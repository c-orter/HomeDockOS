"""
hd_UIContainerTerminal.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import os
import re
import json
import time
import queue
import socket
import asyncio
import secrets
import threading

import docker

from urllib.parse import parse_qs
from concurrent.futures import TimeoutError as FutureTimeoutError

from flask import jsonify, request
from flask_login import current_user, login_required

from pymodules.hd_ClassDockerClientManager import DockerClientManager
from pymodules.hd_FunctionsConfig import read_config
from pymodules.hd_HomedockNetwork import own_container
from pymodules.hd_FunctionsHostSelector import is_docker
from pymodules import hd_HostShell as host_shell

TERMINAL_WS_PATH = "/api/container-terminal/ws"

TICKET_TTL = 30
MAX_SESSIONS = 16
READ_CHUNK = 65536
OUTPUT_QUEUE_SIZE = 64
MAX_INPUT_FRAME = 1024 * 1024
MIN_SIZE = 1
MAX_COLS = 1000
MAX_ROWS = 500

PROBE_INTERPRETERS = ("/bin/sh", "/bin/bash", "/busybox/sh")
SHELL_CANDIDATES = ("/bin/bash", "/usr/bin/bash", "/bin/zsh", "/usr/bin/zsh", "/bin/ash", "/bin/sh", "/busybox/sh")
WINDOWS_SHELLS = ("powershell.exe", "cmd.exe")

USER_MODES = {"default": None, "root": "0:0"}

PID_MARKER_PREFIX = b"\x1b]7337;"
PID_MARKER_RE = re.compile(rb"\x1b\]7337;(\d+)\x07")
PID_MARKER_MAX = 64

USER_PROBE_PREFIX = "@user:"

_PROBE_SCRIPT = "for s in " + " ".join(SHELL_CANDIDATES) + ' ; do [ -x "$s" ] && echo "$s"; done; u=$(id -un 2>/dev/null) || u=$(id -u 2>/dev/null); echo "' + USER_PROBE_PREFIX + '$u"'

_RC_ALIASES = r"""
if ! alias ls >/dev/null 2>&1 && ls --color=auto -d / >/dev/null 2>&1; then alias ls='ls --color=auto'; fi
if ! alias grep >/dev/null 2>&1 && echo x | grep --color=auto x >/dev/null 2>&1; then alias grep='grep --color=auto'; fi
"""

_BASH_RC = r"""
exec 3<&-
if [ -f /etc/bash.bashrc ]; then . /etc/bash.bashrc; fi
if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; elif [ -f /etc/bashrc ]; then . /etc/bashrc; fi
case "$PS1" in
*'\e['*|*'\033['*|*'\E['*|*$'\033'*) ;;
*)
  if [ "$(id -u 2>/dev/null)" = 0 ]; then __hd_c='1;31'; else __hd_c='1;32'; fi
  __hd_u=$(id -un 2>/dev/null) || __hd_u=$(id -u 2>/dev/null)
  PS1='\[\033['"$__hd_c"'m\]'"$__hd_u"'@\h\[\033[0m\]:\[\033[1;34m\]\w\[\033[0m\]\$ '
  unset __hd_c __hd_u
  ;;
esac
""" + _RC_ALIASES

_SH_RC = r"""
exec 3<&-
if [ -n "$HOMEDOCK_ENV" ]; then ENV="$HOMEDOCK_ENV"; export ENV; else unset ENV; fi
unset HOMEDOCK_ENV
if [ -n "$ENV" ] && [ -r "$ENV" ]; then . "$ENV"; fi
__hd_esc=$(printf '\033')
case "$PS1" in
*"$__hd_esc"*|*'\033['*|*'\e['*) ;;
*)
  if [ "$(id -u 2>/dev/null)" = 0 ]; then __hd_c='1;31'; __hd_p='#'; else __hd_c='1;32'; __hd_p='$'; fi
  __hd_u=$(id -un 2>/dev/null) || __hd_u=$(id -u 2>/dev/null)
  case "$BASH_VERSION:$(readlink /proc/$$/exe 2>/dev/null)" in
  ?*:*|*busybox*) PS1='\[\033['"$__hd_c"'m\]'"$__hd_u"'@\h\[\033[0m\]:\[\033[1;34m\]\w\[\033[0m\]\$ ' ;;
  *) PS1="$__hd_esc[${__hd_c}m$__hd_u@$(uname -n 2>/dev/null)$__hd_esc[0m:$__hd_esc[1;34m"'$PWD'"$__hd_esc[0m$__hd_p " ;;
  esac
  unset __hd_c __hd_p __hd_u
  ;;
esac
unset __hd_esc
""" + _RC_ALIASES

_LAUNCH_SCRIPT = (
    r"""printf '\033]7337;%s\007' "$$"
shell="$1"
case "${shell##*/}" in
bash)
  exec "$shell" --rcfile /dev/fd/3 3<<'HOMEDOCK_RC'
"""
    + _BASH_RC
    + r"""
HOMEDOCK_RC
  ;;
ash|sh|dash)
  HOMEDOCK_ENV="${ENV-}"
  ENV=/dev/fd/3
  export HOMEDOCK_ENV ENV
  exec "$shell" 3<<'HOMEDOCK_RC'
"""
    + _SH_RC
    + r"""
HOMEDOCK_RC
  ;;
esac
exec "$shell"
"""
)
_HANGUP_SCRIPT = 'kill -HUP "$1" 2>/dev/null; sleep 1; kill -0 "$1" 2>/dev/null && kill -KILL "$1" 2>/dev/null; exit 0'

_tickets = {}
_tickets_lock = threading.Lock()

_sessions = set()
_sessions_lock = threading.Lock()


class TerminalError(Exception):
    def __init__(self, code, status=400, detail=""):
        super().__init__(code)
        self.code = code
        self.status = status
        self.detail = detail


def _client():
    return DockerClientManager.get_instance().get_client()


def _get_running_container(container_name):
    if not container_name or not isinstance(container_name, str):
        raise TerminalError("invalid_request")

    try:
        container = _client().containers.get(container_name)
    except docker.errors.NotFound:
        raise TerminalError("not_found", 404)
    except docker.errors.DockerException as e:
        raise TerminalError("docker_error", 500, str(e))

    status = container.attrs.get("State", {}).get("Status", container.status)

    if status == "paused":
        raise TerminalError("paused", 409)

    if status != "running":
        raise TerminalError("not_running", 409)

    return container


def _is_windows_container(container):
    return (container.attrs.get("Platform") or "").lower() == "windows"


def _probe_shells(container):
    if _is_windows_container(container):
        return None, list(WINDOWS_SHELLS), ""

    for interpreter in PROBE_INTERPRETERS:
        try:
            result = container.exec_run([interpreter, "-c", _PROBE_SCRIPT], stdout=True, stderr=False, user="")
        except docker.errors.APIError as e:
            if e.status_code == 409:
                raise TerminalError("not_running", 409)
            continue

        if result.exit_code in (126, 127) and not result.output.startswith(b"/"):
            continue

        shells = []
        seen = set()
        username = ""

        for line in result.output.decode("utf-8", "replace").splitlines():
            path = line.strip()
            name = path.rsplit("/", 1)[-1]

            if path.startswith(USER_PROBE_PREFIX):
                username = path[len(USER_PROBE_PREFIX) :]
                continue

            if path in SHELL_CANDIDATES and name not in seen:
                seen.add(name)
                shells.append(path)

        if interpreter not in shells:
            shells.append(interpreter)

        return interpreter, shells, username

    raise TerminalError("no_shell", 422)


def _resolve_shell(requested, shells):
    if not requested or requested == "auto":
        return shells[0]

    if requested in shells:
        return requested

    raise TerminalError("invalid_shell")


def _clamp_size(value, upper, fallback):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback

    return max(MIN_SIZE, min(upper, number))


def _prune_tickets(now):
    for key in [key for key, entry in _tickets.items() if entry["expires"] < now]:
        _tickets.pop(key, None)


def _issue_ticket(entry):
    ticket = secrets.token_urlsafe(32)
    now = time.monotonic()

    with _tickets_lock:
        _prune_tickets(now)
        entry["expires"] = now + TICKET_TTL
        _tickets[ticket] = entry

    return ticket


def _consume_ticket(ticket):
    if not ticket:
        return None

    with _tickets_lock:
        entry = _tickets.pop(ticket, None)

    if entry is None or entry["expires"] < time.monotonic():
        return None

    return entry


def _active_session_count():
    with _sessions_lock:
        return sum(1 for session in _sessions if not session.entry.get("host"))


def _active_host_count():
    with _sessions_lock:
        return sum(1 for session in _sessions if session.entry.get("host"))


@login_required
def api_container_terminal_targets():
    """What the terminal picker offers: HomeDock's own container (when it runs in one) and every container."""

    try:
        client = _client()
        listed = client.containers.list(all=True)
        own = own_container(client) if is_docker else None
    except docker.errors.DockerException as e:
        return jsonify({"success": False, "code": "docker_error", "detail": str(e)}), 500

    containers = sorted(({"name": c.name, "status": c.status} for c in listed), key=lambda item: item["name"].lower())

    return jsonify({"success": True, "homedock": own.name if own else None, "containers": containers, "host": _host_target(client, own)})


def _host_target(client, own):
    """The host option, present only while the Settings switch is on."""

    if not host_shell.host_shell_enabled():
        return None

    reason = ""

    if is_docker and own is None:
        reason = "HomeDock OS could not find its own container to start the host helper from."
    elif is_docker and host_shell.engine_is_rootless(client):
        reason = "The container engine runs rootless, so it cannot enter the host."

    return {"available": not reason, "reason": reason, "requires_2fa": bool(read_config().get("2fa_enabled"))}


def _host_session(payload, client_ip):
    if not host_shell.host_shell_enabled():
        raise TerminalError("host_disabled", 403)

    if _active_host_count() >= host_shell.HOST_MAX_SESSIONS:
        raise TerminalError("host_limit", 429)

    try:
        host_shell.authorize(client_ip, payload.get("password"), payload.get("code"))
    except host_shell.HostShellError as e:
        raise TerminalError(e.code, e.status)

    image = ""

    if is_docker:
        own = own_container(_client())

        if own is None or host_shell.engine_is_rootless(_client()):
            raise TerminalError("host_unavailable", 422)

        image = own.attrs.get("Config", {}).get("Image") or own.image.tags[0]

    return {
        "host": True,
        "kind": "docker" if is_docker else "pty",
        "image": image,
        "container_id": "host",
        "container_name": "Host",
        "interpreter": None,
        "shell": "login",
        "user": "0:0",
        "user_mode": "root",
        "username": "root" if is_docker else (os.environ.get("USER") or "host"),
        "windows": False,
        "ip": client_ip,
        "operator": current_user.get_id(),
        "cols": _clamp_size(payload.get("cols"), MAX_COLS, 80),
        "rows": _clamp_size(payload.get("rows"), MAX_ROWS, 24),
    }


def _require_gates_for_own_container(container, payload, client_ip):
    """HomeDock's own container mounts the Docker socket, so a shell in it is as strong as a host shell and needs the same switch, fresh password and 2FA."""

    if not is_docker:
        return

    own = own_container(_client())

    if own is None or own.id != container.id:
        return

    if not host_shell.host_shell_enabled():
        raise TerminalError("host_disabled", 403)

    try:
        host_shell.authorize(client_ip, payload.get("password"), payload.get("code"))
    except host_shell.HostShellError as e:
        raise TerminalError(e.code, e.status)


@login_required
def api_container_terminal_session():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        payload = {}

    container_name = payload.get("containerName")
    requested_shell = payload.get("shell") or "auto"
    user_mode = payload.get("user") or "default"

    if not isinstance(user_mode, str) or user_mode not in USER_MODES:
        return jsonify({"success": False, "code": "invalid_user"}), 400

    if payload.get("host"):
        try:
            entry = _host_session(payload, request.remote_addr)
        except TerminalError as e:
            return jsonify({"success": False, "code": e.code, "detail": e.detail}), e.status

        ticket = _issue_ticket(entry)

        return jsonify({"success": True, "ticket": ticket, "shell": "login", "shells": [], "user": "root", "path": TERMINAL_WS_PATH})

    if _active_session_count() >= MAX_SESSIONS:
        return jsonify({"success": False, "code": "limit"}), 429

    try:
        container = _get_running_container(container_name)
        _require_gates_for_own_container(container, payload, request.remote_addr)
        interpreter, shells, default_username = _probe_shells(container)
        shell = _resolve_shell(requested_shell, shells)
    except TerminalError as e:
        return jsonify({"success": False, "code": e.code, "detail": e.detail}), e.status

    ticket = _issue_ticket(
        {
            "container_id": container.id,
            "container_name": container.name,
            "interpreter": interpreter,
            "shell": shell,
            "user": USER_MODES[user_mode],
            "user_mode": user_mode,
            "username": "root" if user_mode == "root" else default_username,
            "windows": _is_windows_container(container),
            "cols": _clamp_size(payload.get("cols"), MAX_COLS, 80),
            "rows": _clamp_size(payload.get("rows"), MAX_ROWS, 24),
        }
    )

    return jsonify({"success": True, "ticket": ticket, "shell": shell, "shells": shells, "user": user_mode, "path": TERMINAL_WS_PATH})


class TerminalSession:
    def __init__(self, entry):
        self.entry = entry
        self.api = _client().api
        self.exec_id = None
        self.sock = None
        self.raw = None
        self.pid = None
        self.closed = False
        self.writes = queue.Queue()
        self.last_input = time.monotonic()
        self._lock = threading.Lock()

    def _environment(self, container_env):
        names = {item.split("=", 1)[0] for item in container_env or []}
        environment = {"TERM": "xterm-256color", "COLORTERM": "truecolor"}

        if not names.intersection({"LANG", "LC_ALL", "LC_CTYPE"}):
            environment["LANG"] = "C.UTF-8"

        return environment

    def _prepare(self):
        """(container id, command, container env, user) for the exec this session runs."""

        entry = self.entry
        container = _client().containers.get(entry["container_id"])

        if entry["windows"]:
            command = [entry["shell"]]
        else:
            command = [entry["interpreter"], "-c", _LAUNCH_SCRIPT, "homedock-terminal", entry["shell"]]

        return container.id, command, container.attrs.get("Config", {}).get("Env"), entry["user"] or ""

    def open(self):
        entry = self.entry
        container_id, command, container_env, user = self._prepare()

        created = self.api.exec_create(container_id, command, stdout=True, stderr=True, stdin=True, tty=True, environment=self._environment(container_env), user=user)

        self.exec_id = created["Id"]
        self.sock = self.api.exec_start(self.exec_id, tty=True, socket=True)
        self.raw = getattr(self.sock, "_sock", self.sock)

        try:
            self.raw.settimeout(None)
        except Exception:
            pass

        with _sessions_lock:
            _sessions.add(self)

        self.resize(entry["cols"], entry["rows"])

    def resize(self, cols, rows):
        if self.closed or not self.exec_id:
            return

        try:
            self.api.exec_resize(self.exec_id, height=_clamp_size(rows, MAX_ROWS, 24), width=_clamp_size(cols, MAX_COLS, 80))
        except Exception:
            pass

    def recv(self):
        try:
            return self.raw.recv(READ_CHUNK)
        except (OSError, ValueError, AttributeError):
            return b""

    def write_loop(self):
        while True:
            data = self.writes.get()

            if data is None or self.closed:
                return

            try:
                self.raw.sendall(data)
            except (OSError, ValueError, AttributeError):
                return

    def exit_code(self):
        if not self.exec_id:
            return None

        for _ in range(10):
            try:
                info = self.api.exec_inspect(self.exec_id)
            except Exception:
                return None

            if not info.get("Running"):
                return info.get("ExitCode")

            time.sleep(0.1)

        return None

    def is_running(self):
        try:
            return bool(self.api.exec_inspect(self.exec_id).get("Running"))
        except Exception:
            return False

    def hangup(self):
        if self.entry["windows"] or not self.pid or not self.exec_id or not self.is_running():
            return

        try:
            container = _client().containers.get(self.entry["container_id"])
            container.exec_run([self.entry["interpreter"], "-c", _HANGUP_SCRIPT, "homedock-terminal", str(self.pid)], user="0:0", detach=True)
        except Exception:
            pass

    def close(self):
        with self._lock:
            if self.closed:
                return
            self.closed = True

        self.writes.put(None)

        for target in (self.raw, self.sock):
            if target is None:
                continue

            try:
                target.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass

            try:
                target.close()
            except Exception:
                pass

        with _sessions_lock:
            _sessions.discard(self)


class HostDockerSession(TerminalSession):
    """A shell on the host: a short-lived privileged helper in the host's pid space runs nsenter into pid 1."""

    helper = None
    removal = None

    def _prepare(self):
        self.helper = host_shell.start_helper(_client(), self.entry["image"])

        return self.helper.id, host_shell.NSENTER_COMMAND, ["HOME=/root"], "0:0"

    def _environment(self, container_env):
        return {**super()._environment(container_env), "HOME": "/root"}

    def close(self):
        super().close()

        helper, self.helper = self.helper, None

        if helper is not None:
            self.removal = threading.Thread(target=_remove_quietly, args=(helper,), name="hd-host-helper-removal", daemon=True)
            self.removal.start()


def _remove_quietly(container):
    try:
        container.remove(force=True)
    except Exception:
        pass


class HostPtySession(TerminalSession):
    """A shell on the machine HomeDock runs on directly, when it is not in a container: a local pty."""

    def __init__(self, entry):
        self.entry = entry
        self.exec_id = "pty"
        self.sock = None
        self.raw = None
        self.process = None
        self.pid = None
        self.closed = False
        self.writes = queue.Queue()
        self.last_input = time.monotonic()
        self._lock = threading.Lock()

    def open(self):
        self.process, fd = host_shell.spawn_pty(self.entry["cols"], self.entry["rows"])
        self.pid = self.process.pid
        self.raw = host_shell.FdSocket(fd)

        with _sessions_lock:
            _sessions.add(self)

    def resize(self, cols, rows):
        if self.closed or self.raw is None:
            return

        try:
            host_shell.resize_pty(self.raw.fd, _clamp_size(cols, MAX_COLS, 80), _clamp_size(rows, MAX_ROWS, 24))
        except OSError:
            pass

    def exit_code(self):
        try:
            return self.process.wait(timeout=1)
        except Exception:
            return None

    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def hangup(self):
        pass

    def close(self):
        with self._lock:
            if self.closed:
                return

        if self.process is not None and self.process.poll() is None:
            host_shell.hang_up(self.process)

        super().close()


def _make_session(entry):
    if not entry.get("host"):
        return TerminalSession(entry)

    return HostDockerSession(entry) if entry["kind"] == "docker" else HostPtySession(entry)


def _strip_pid_marker(session, pending):
    match = PID_MARKER_RE.search(pending)

    if match:
        session.pid = int(match.group(1))
        return pending[: match.start()] + pending[match.end() :], True

    head = pending.lstrip(b"\r\n")

    if len(pending) >= PID_MARKER_MAX or not (PID_MARKER_PREFIX.startswith(head[: len(PID_MARKER_PREFIX)]) or head.startswith(PID_MARKER_PREFIX)):
        return pending, True

    return pending, False


def _reader_thread(session, loop, output):
    pending = b""
    marker_resolved = session.entry["windows"] or bool(session.entry.get("host"))

    def deliver(data):
        future = asyncio.run_coroutine_threadsafe(output.put(data), loop)

        while True:
            try:
                future.result(timeout=1)
                return True
            except FutureTimeoutError:
                if session.closed:
                    future.cancel()
                    return False

    try:
        while True:
            data = session.recv()

            if not data:
                break

            if not marker_resolved:
                pending += data
                pending, marker_resolved = _strip_pid_marker(session, pending)

                if not marker_resolved:
                    continue

                data, pending = pending, b""

                if not data:
                    continue

            if not deliver(data):
                return

        if pending:
            deliver(pending)

    except Exception:
        pass

    finally:
        try:
            deliver(None)
        except Exception:
            pass


async def _send_json(send, payload):
    await send({"type": "websocket.send", "text": json.dumps(payload)})


async def _reject(send, code):
    await send({"type": "websocket.accept"})
    await _send_json(send, {"type": "error", "code": code})
    await send({"type": "websocket.close", "code": 4000})


async def _pump_output(output, send):
    while True:
        data = await output.get()

        if data is None:
            return "exited"

        await send({"type": "websocket.send", "bytes": data})


async def _pump_input(session, receive, loop):
    while True:
        message = await receive()
        kind = message["type"]

        if kind == "websocket.disconnect":
            return "disconnected"

        if kind != "websocket.receive":
            continue

        data = message.get("bytes")

        if data is not None:
            if 0 < len(data) <= MAX_INPUT_FRAME:
                session.last_input = time.monotonic()
                session.writes.put(data)
            continue

        try:
            control = json.loads(message.get("text") or "")
        except ValueError:
            continue

        if not isinstance(control, dict):
            continue

        if control.get("type") == "resize":
            await loop.run_in_executor(None, session.resize, control.get("cols"), control.get("rows"))


async def _watch_idle(session):
    """Ends a host session once nothing has been typed into it for the idle limit."""

    while True:
        remaining = host_shell.HOST_IDLE_TIMEOUT - (time.monotonic() - session.last_input)

        if remaining <= 0:
            return "idle"

        await asyncio.sleep(min(remaining, 30))


async def _cancel(tasks):
    for task in tasks:
        task.cancel()

    for task in tasks:
        try:
            await task
        except BaseException:
            pass


async def _serve_terminal(scope, receive, send):
    message = await receive()

    if message["type"] != "websocket.connect":
        return

    query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    entry = _consume_ticket((query.get("ticket") or [""])[0])

    if entry is None:
        await _reject(send, "unauthorized")
        return

    is_host = bool(entry.get("host"))

    if is_host and not host_shell.host_shell_enabled():
        await _reject(send, "host_disabled")
        return

    if is_host and _active_host_count() >= host_shell.HOST_MAX_SESSIONS:
        await _reject(send, "host_limit")
        return

    if not is_host and _active_session_count() >= MAX_SESSIONS:
        await _reject(send, "limit")
        return

    loop = asyncio.get_running_loop()
    session = _make_session(entry)

    try:
        await loop.run_in_executor(None, session.open)
    except docker.errors.APIError as e:
        session.close()
        await _reject(send, "not_running" if e.status_code == 409 else "exec_failed")
        return
    except Exception:
        session.close()
        await _reject(send, "exec_failed")
        return

    opened = time.monotonic()

    if is_host:
        host_shell.audit("open", entry["ip"], entry["operator"], "host", entry["kind"])

    await send({"type": "websocket.accept"})
    await _send_json(send, {"type": "ready", "shell": entry["shell"], "user": entry["user_mode"], "username": entry["username"], "container": entry["container_name"], "id": entry["container_id"][:12]})

    output = asyncio.Queue(maxsize=OUTPUT_QUEUE_SIZE)

    threading.Thread(target=_reader_thread, args=(session, loop, output), name="hd-terminal-reader", daemon=True).start()
    threading.Thread(target=session.write_loop, name="hd-terminal-writer", daemon=True).start()

    output_task = asyncio.ensure_future(_pump_output(output, send))
    input_task = asyncio.ensure_future(_pump_input(session, receive, loop))
    idle_task = asyncio.ensure_future(_watch_idle(session)) if is_host else None

    outcome = "disconnected"

    try:
        done, pending = await asyncio.wait({output_task, input_task, *([idle_task] if idle_task else [])}, return_when=asyncio.FIRST_COMPLETED)

        await _cancel(pending)

        if output_task in done and not output_task.cancelled() and output_task.exception() is None:
            outcome = output_task.result()
        elif idle_task in done and not idle_task.cancelled() and idle_task.exception() is None:
            outcome = "idle"

    except asyncio.CancelledError:
        await _cancel([output_task, input_task])
        raise

    finally:
        if outcome != "exited":
            await loop.run_in_executor(None, session.hangup)

        session.close()

        if is_host:
            host_shell.audit("close", entry["ip"], entry["operator"], "host", f"{outcome} after {int(time.monotonic() - opened)}s")

    if outcome == "idle":
        try:
            await _send_json(send, {"type": "exit", "code": None, "reason": "idle"})
            await send({"type": "websocket.close", "code": 1000})
        except Exception:
            pass

    elif outcome == "exited":
        code = await loop.run_in_executor(None, session.exit_code)

        try:
            await _send_json(send, {"type": "exit", "code": code})
            await send({"type": "websocket.close", "code": 1000})
        except Exception:
            pass


def shutdown_terminal_sessions():
    with _sessions_lock:
        active = list(_sessions)

    for session in active:
        session.close()

    for session in active:
        removal = getattr(session, "removal", None)

        if removal is not None:
            removal.join(timeout=5)


def wrap_asgi_with_container_terminal(downstream):

    async def terminal_router(scope, receive, send):
        if scope["type"] == "websocket" and scope.get("path") == TERMINAL_WS_PATH:
            await _serve_terminal(scope, receive, send)
            return

        await downstream(scope, receive, send)

    return terminal_router

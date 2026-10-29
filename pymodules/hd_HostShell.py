"""
hd_HostShell.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import os
import pty
import fcntl
import struct
import signal
import termios
import threading
import subprocess

from collections import defaultdict
from datetime import datetime, timedelta

import bcrypt
import docker

from pymodules.hd_FunctionsConfig import read_config
from pymodules.hd_FunctionsGlobals import current_directory
from pymodules.hd_2FAInternalHandler import verify_2fa_code, save_backup_codes

HOST_MAX_SESSIONS = 2
HOST_IDLE_TIMEOUT = 30 * 60

MAX_AUTH_FAILURES = 5
AUTH_FAILURE_WINDOW = timedelta(minutes=5)

HELPER_LABEL = "homedock.host-shell"

# Enter every namespace of the host's pid 1, then a login shell (bash when the host has it)
NSENTER_COMMAND = ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--", "sh", "-c", "if command -v bash >/dev/null 2>&1; then exec bash -l; else exec sh -l; fi"]

audit_file = os.path.join(current_directory, "logs", "hostshell.log")

_failures = defaultdict(list)
_audit_lock = threading.Lock()


class HostShellError(Exception):
    def __init__(self, code, status=400, detail=""):
        super().__init__(code)
        self.code = code
        self.status = status
        self.detail = detail


def host_shell_enabled():
    return bool(read_config().get("host_shell_enabled", False))


def engine_is_rootless(client):
    try:
        options = client.info().get("SecurityOptions") or []
    except Exception:
        return False

    return any("rootless" in str(option).lower() for option in options)


def authorize(ip, password, code):
    """A fresh password, and a 2FA code when 2FA is on, for every single host session."""

    now = datetime.now()
    _failures[ip] = [moment for moment in _failures[ip] if moment > now - AUTH_FAILURE_WINDOW]

    if len(_failures[ip]) >= MAX_AUTH_FAILURES:
        raise HostShellError("too_many_attempts", 429)

    config = read_config()

    valid = isinstance(password, str) and password != "" and bcrypt.checkpw(password.encode("utf-8"), config["user_password"])

    if valid and config.get("2fa_enabled"):
        backup_text = config.get("2fa_backup_codes", "")
        backup_codes = backup_text.split(",") if backup_text else []

        accepted, used_backup, remaining = verify_2fa_code(code if isinstance(code, str) else "", config.get("2fa_secret"), backup_codes)

        if accepted and used_backup and remaining is not None:
            save_backup_codes(remaining)

        valid = accepted

    if not valid:
        _failures[ip].append(now)
        raise HostShellError("auth_failed", 401)

    _failures.pop(ip, None)


def clean_field(value):
    return str(value).replace("***", "*").replace("\r", " ").replace("\n", " ")[:120]


def audit(event, ip, user, target, detail=""):
    """One line per open or close: when, what, who, from where. Never what was typed."""

    line = "***".join([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), clean_field(event), clean_field(ip), clean_field(user), clean_field(target), clean_field(detail)])

    try:
        with _audit_lock:
            os.makedirs(os.path.dirname(audit_file), exist_ok=True)

            with open(audit_file, "a") as handle:
                handle.write(line + "\n")
    except OSError:
        pass


def read_audit(limit=500):
    entries = []

    try:
        with open(audit_file, "r") as handle:
            lines = handle.readlines()
    except OSError:
        return entries

    for line in reversed(lines[-limit:]):
        parts = line.rstrip("\n").split("***")

        if len(parts) == 6:
            entries.append(dict(zip(("timestamp", "event", "ip", "user", "target", "detail"), parts)))

    return entries


def cleanup_host_shell_helpers():
    from pymodules.hd_ClassDockerClientManager import DockerClientManager

    try:
        cleanup_helpers(DockerClientManager.get_instance().get_client())
    except Exception:
        pass


def cleanup_helpers(client):
    """Helpers are removed when their session ends; this catches ones a crash left behind."""

    try:
        for container in client.containers.list(all=True, filters={"label": HELPER_LABEL}):
            container.remove(force=True)
    except docker.errors.DockerException:
        pass


def start_helper(client, own_image):
    return client.containers.run(own_image, detach=True, privileged=True, pid_mode="host", network_mode="none", entrypoint=["tail", "-f", "/dev/null"], labels={HELPER_LABEL: "1"})


class FdSocket:
    """The slice of a socket the terminal pumps use, over a pty master."""

    def __init__(self, fd):
        self.fd = fd

    def recv(self, size):
        return os.read(self.fd, size)

    def sendall(self, data):
        view = memoryview(data)

        while view:
            view = view[os.write(self.fd, view) :]

    def shutdown(self, how):
        pass

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


def login_shell():
    for candidate in (os.environ.get("SHELL"), "/bin/bash", "/bin/sh"):
        if candidate and os.access(candidate, os.X_OK):
            return candidate

    return "/bin/sh"


def spawn_pty(cols, rows):
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    shell = login_shell()
    environment = {**os.environ, "TERM": "xterm-256color", "COLORTERM": "truecolor"}

    process = subprocess.Popen([shell, "-l"], stdin=slave, stdout=slave, stderr=slave, start_new_session=True, close_fds=True, env=environment, preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0))
    os.close(slave)

    return process, master


def resize_pty(fd, cols, rows):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def hang_up(process):
    """SIGHUP the whole session, then SIGKILL what ignored it."""

    try:
        os.killpg(process.pid, signal.SIGHUP)
    except (ProcessLookupError, PermissionError):
        return

    def reap():
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    threading.Thread(target=reap, daemon=True).start()

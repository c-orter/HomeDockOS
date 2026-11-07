"""
hd_BrowserRuntime.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import json
import os
import socket
import threading
import time
import urllib.request

import docker

from pymodules import hd_BrowserAllowlist as allowlist
from pymodules import hd_BrowserSettings as browser_settings
from pymodules.hd_BrowserEngine import CHROMIUM_USER, INIT_CAPABILITIES, PROXY_PORT, SANDBOX_PROBE, EgressProxyImage, ImageUnavailable, SelkiesChromiumEngine
from pymodules.hd_ClassDockerClientManager import DockerClientManager
from pymodules.hd_FunctionsGlobals import running_OS
from pymodules.hd_FunctionsHostSelector import is_docker
from pymodules.hd_HomedockNetwork import connect_container, own_container

BROWSER_LABEL = "homedock.browser"

CONTAINER_NAME = "homedock-browser"
NETWORK_NAME = "homedock_browser"
EGRESS_NETWORK_NAME = "homedock_browser_egress"
APP_NETWORK_NAME = "homedock_network"
PROXY_CONTAINER_NAME = "homedock-browser-proxy"
PROFILE_VOLUME = "homedock_browser_profile"

PROXY_MEMORY_LIMIT = "128m"
PROXY_PIDS_LIMIT = 128
PROXY_NANO_CPUS = 500_000_000
PROXY_START_TIMEOUT = 20

SECCOMP_PROFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hd_BrowserSeccomp.json")

START_TIMEOUT = 90
POLL_INTERVAL = 1

BUSY_PHASES = ("pulling", "building", "checking", "starting")

_engine = SelkiesChromiumEngine()
_proxy_image = EgressProxyImage(os.path.join(os.path.dirname(os.path.abspath(__file__)), "hd_BrowserEgressProxy.py"))

_state = {"phase": "stopped", "code": "", "detail": "", "progress": None}

# After a failed pull the running browser is left alone for this long, so an offline server does not restart it on every open.
PULL_RETRY_SECONDS = 900
_pull_failed_at = {"at": None}
_lock = threading.Lock()
_probed = set()


class BrowserError(Exception):
    def __init__(self, code, detail=""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def engine():
    return _engine


def _client():
    return DockerClientManager.get_instance().get_client()


def docker_available():
    try:
        return bool(_client().ping())
    except Exception:
        return False


def _set_phase(phase, code="", detail=""):
    with _lock:
        _state.update(phase=phase, code=code, detail=detail, progress=None)


def _set_progress(percent):
    with _lock:
        _state["progress"] = percent


def _ensure_image(image, client):
    """The reference to run, with a failed pull turned into an error the window can show."""

    try:
        reference = image.ensure_image(client, progress=lambda phase: _set_phase(phase), on_percent=_set_progress)
    except ImageUnavailable as e:
        _pull_failed_at["at"] = time.monotonic()
        raise BrowserError(e.code, e.detail)

    if reference != image.image_reference():
        _pull_failed_at["at"] = time.monotonic()

    return reference


def seccomp_profile():
    """The profile as the compact JSON the Docker API takes inline: Docker's default plus the user-namespace calls Chromium's sandbox needs."""

    with open(SECCOMP_PROFILE, "r", encoding="utf-8") as f:
        return json.dumps(json.load(f), separators=(",", ":"))


def _read_sysctl(name):
    try:
        with open(f"/proc/sys/{name}", "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def sandbox_cause():
    """Names the likeliest reason an unprivileged process cannot create a user namespace here."""

    if _read_sysctl("kernel/apparmor_restrict_unprivileged_userns") == "1":
        return "AppArmor restricts unprivileged user namespaces on this host (kernel.apparmor_restrict_unprivileged_userns=1)."

    if _read_sysctl("user/max_user_namespaces") == "0":
        return "User namespaces are switched off on this host (user.max_user_namespaces=0)."

    if _read_sysctl("kernel/unprivileged_userns_clone") == "0":
        return "Unprivileged user namespaces are switched off on this host (kernel.unprivileged_userns_clone=0)."

    return "The container engine or the kernel blocked user namespaces for the browser's seccomp profile."


def _hardening():
    """The security settings are fixed and not editable from the UI. Only the resource limits come from Settings, validated to a range, and they apply on the next start."""

    limits = browser_settings.limits()

    return {
        "cap_drop": ["ALL"],
        "cap_add": list(INIT_CAPABILITIES),
        "security_opt": ["no-new-privileges", f"seccomp={seccomp_profile()}"],
        "mem_limit": limits["mem_limit"],
        "memswap_limit": limits["mem_limit"],
        "pids_limit": limits["pids_limit"],
        "nano_cpus": limits["nano_cpus"],
        "shm_size": limits["shm_size"],
        "privileged": False,
    }


def check_sandbox(client, image=None):
    """Refuses to start unless an unprivileged process in the container can create the namespaces Chromium's sandbox uses. There is no --no-sandbox fallback."""

    image = image or _engine.image_reference()

    if image in _probed:
        return

    probe = _hardening()
    probe.pop("shm_size")

    try:
        client.containers.run(image, command=None, entrypoint=SANDBOX_PROBE, user=CHROMIUM_USER, network_mode="none", detach=False, remove=True, **probe)
    except docker.errors.ContainerError:
        raise BrowserError("sandbox_unavailable", sandbox_cause())
    except docker.errors.DockerException as e:
        raise BrowserError("docker_error", str(e))

    _probed.add(image)


def _ensure_network(client):
    found = [n for n in client.networks.list(names=[NETWORK_NAME]) if n.name == NETWORK_NAME]

    if found:
        if not found[0].attrs.get("Internal"):
            raise BrowserError("network_unsafe", f"The '{NETWORK_NAME}' network exists but is not internal, so the browser would have a direct route out. Remove it and try again.")

        return found[0]

    return client.networks.create(NETWORK_NAME, driver="bridge", internal=True, labels={BROWSER_LABEL: "1"})


def _ensure_egress_network(client):
    """The proxy's own way out. Only the proxy is ever attached to it."""

    found = [n for n in client.networks.list(names=[EGRESS_NETWORK_NAME]) if n.name == EGRESS_NETWORK_NAME]

    if found:
        return found[0]

    return client.networks.create(EGRESS_NETWORK_NAME, driver="bridge", labels={BROWSER_LABEL: "1"})


def _proxy_hardening():
    return {
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"],
        "read_only": True,
        "mem_limit": PROXY_MEMORY_LIMIT,
        "memswap_limit": PROXY_MEMORY_LIMIT,
        "pids_limit": PROXY_PIDS_LIMIT,
        "nano_cpus": PROXY_NANO_CPUS,
        "privileged": False,
    }


def _start_proxy(client, internal_network):
    """Runs the egress proxy: created on the network that reaches the internet, then attached to the internal one under a fixed name the browser dials."""

    proxy_reference = _ensure_image(_proxy_image, client)

    egress = _ensure_egress_network(client)

    stale = _existing(client, PROXY_CONTAINER_NAME)

    if stale is not None:
        _remove(stale)

    rules = allowlist.proxy_rules(_deny_addresses(client))

    proxy = client.containers.create(
        proxy_reference,
        name=PROXY_CONTAINER_NAME,
        detach=True,
        network=egress.name,
        environment={"HD_EGRESS_RULES": json.dumps(rules, separators=(",", ":"))},
        labels={BROWSER_LABEL: "1"},
        restart_policy={"Name": "no"},
        **_proxy_hardening(),
    )

    try:
        internal_network.connect(proxy, aliases=[PROXY_CONTAINER_NAME])

        # Allowed apps live on the shared app network. Only the proxy joins it, and the proxy still refuses everything the list does not name.
        if allowlist.has_apps():
            _join_app_network(client, proxy)

        proxy.start()
        _wait_proxy(proxy)
    except Exception:
        _remove(proxy)
        raise


def _join_app_network(client, proxy):
    try:
        client.networks.get(APP_NETWORK_NAME).connect(proxy)
    except docker.errors.NotFound:
        pass


def _deny_addresses(client):
    """Addresses the allowlist can never open: HomeDock itself, and the host's side of the browser's networks. Best effort from where HomeDock stands."""

    addresses = set()

    try:
        if is_docker:
            own = own_container(client)

            if own is not None:
                own.reload()

                for network in own.attrs.get("NetworkSettings", {}).get("Networks", {}).values():
                    addresses.update(a for a in (network.get("IPAddress"), network.get("GlobalIPv6Address")) if a)

        for name in (NETWORK_NAME, EGRESS_NETWORK_NAME, "bridge"):
            for found in client.networks.list(names=[name]):
                for config in (found.attrs.get("IPAM") or {}).get("Config") or []:
                    if config.get("Gateway"):
                        addresses.add(config["Gateway"])
    except docker.errors.DockerException:
        pass

    if is_docker:
        try:
            addresses.add(socket.gethostbyname("host.docker.internal"))
        except OSError:
            pass
    else:
        import psutil

        for entries in psutil.net_if_addrs().values():
            addresses.update(entry.address.split("%")[0] for entry in entries if entry.family in (socket.AF_INET, socket.AF_INET6))

    return addresses


def refresh_proxy():
    """Restarts only the proxy, so a changed allowlist applies at once. Open connections drop and the browser reconnects."""

    client = _client()

    if _existing(client, PROXY_CONTAINER_NAME) is None:
        return False

    _start_proxy(client, _ensure_network(client))

    return True


def reset_profile():
    """Deletes the browser's profile: logins, cookies, history, bookmarks. The browser must not be running."""

    client = _client()

    if _existing(client) is not None:
        raise BrowserError("still_running", "Stop the browser first.")

    try:
        client.volumes.get(PROFILE_VOLUME).remove(force=True)
    except docker.errors.NotFound:
        pass


def _wait_proxy(proxy):
    deadline = time.monotonic() + PROXY_START_TIMEOUT

    while time.monotonic() < deadline:
        proxy.reload()

        if proxy.status == "running":
            return

        if proxy.status in ("exited", "dead"):
            raise BrowserError("proxy_exited", "The browser's egress proxy stopped while starting.")

        time.sleep(0.5)

    raise BrowserError("proxy_timeout", "The browser's egress proxy did not start in time.")


def _ensure_volume(client):
    try:
        client.volumes.get(PROFILE_VOLUME)
    except docker.errors.NotFound:
        client.volumes.create(PROFILE_VOLUME, labels={BROWSER_LABEL: "1"})


def _existing(client, name=CONTAINER_NAME):
    try:
        return client.containers.get(name)
    except docker.errors.NotFound:
        return None


STOP_GRACE_SECONDS = 8


def _remove(container, graceful=False):
    """Removes a container. The browser is asked to stop first, so Chromium can save its session and the next start does not open on a 'did not shut down correctly' prompt."""

    try:
        if graceful and container.status == "running":
            try:
                container.stop(timeout=STOP_GRACE_SECONDS)
            except docker.errors.APIError:
                pass

        container.remove(force=True)
    except docker.errors.NotFound:
        pass


def _reachable_from_here():
    """A native HomeDock dials the container's address on the internal network, which only a Linux host can route to."""

    return is_docker or running_OS == "Linux"


def _address(container, network_name):
    container.reload()

    return container.attrs.get("NetworkSettings", {}).get("Networks", {}).get(network_name, {}).get("IPAddress") or None


def upstream():
    """(host, port) the relay dials, or None while the browser is not running."""

    try:
        container = _existing(_client())

        if container is None or container.status != "running":
            return None

        if is_docker:
            return CONTAINER_NAME, _engine.internal_port

        address = _address(container, NETWORK_NAME)

        return (address, _engine.internal_port) if address else None
    except docker.errors.DockerException:
        return None


def _wait_ready(container):
    deadline = time.monotonic() + START_TIMEOUT

    while time.monotonic() < deadline:
        container.reload()

        if container.status != "running":
            raise BrowserError("exited", "The browser container stopped while starting.")

        target = upstream()

        if target:
            try:
                with urllib.request.urlopen(f"http://{target[0]}:{target[1]}{_engine.health_path}", timeout=2):
                    return
            except OSError:
                pass

        time.sleep(POLL_INTERVAL)

    raise BrowserError("start_timeout", "The browser did not answer in time.")


def _launch():
    client = _client()

    if not _reachable_from_here():
        raise BrowserError("unsupported_platform", "HomeDock OS can only reach the browser from a Linux host or from inside its own container.")

    image = _ensure_image(_engine, client)

    _set_phase("checking")
    check_sandbox(client, image)

    _set_phase("starting")

    network = _ensure_network(client)
    _ensure_volume(client)

    if is_docker:
        own = own_container(client)

        if own is None:
            raise BrowserError("no_own_container", "HomeDock OS could not find its own container to join the browser network.")

        connect_container(network, own)

    _start_proxy(client, network)

    stale = _existing(client)

    if stale is not None:
        _remove(stale, graceful=True)

    container = client.containers.create(
        image,
        name=CONTAINER_NAME,
        detach=True,
        environment=_engine.environment(proxy=f"{PROXY_CONTAINER_NAME}:{PROXY_PORT}"),
        tmpfs=_engine.tmpfs(),
        volumes={PROFILE_VOLUME: {"bind": _engine.config_mount, "mode": "rw"}},
        network=NETWORK_NAME,
        labels={BROWSER_LABEL: "1"},
        restart_policy={"Name": "no"},
        **_hardening(),
    )

    try:
        container.start()
        _wait_ready(container)
    except Exception:
        _remove(container)
        _remove_proxy(client)
        raise


MAX_DETAIL = 300


def readable(error):
    """An engine error as one short line the window can show. Engines sometimes echo what they were given (the whole seccomp profile, for one), which is a wall of JSON to a person."""

    text = getattr(error, "explanation", None) or str(error)
    text = text.replace(seccomp_profile(), "<seccomp profile>")
    text = " ".join(text.split())

    return text if len(text) <= MAX_DETAIL else text[: MAX_DETAIL - 1] + "…"


def _run():
    try:
        _launch()
    except BrowserError as e:
        _set_phase("error", e.code, readable(e.detail))
        return
    except docker.errors.DockerException as e:
        _set_phase("error", "docker_error", readable(e))
        return
    except Exception as e:
        _set_phase("error", "unexpected", readable(e))
        return

    _set_phase("running")


def start():
    """Starts the browser in the background. A second call while it is starting or running does nothing."""

    with _lock:
        if _state["phase"] in BUSY_PHASES:
            return

    # A browser that kept running across a HomeDock restart is joined, not restarted, unless a HomeDock update pinned a newer image.
    container = running_container()

    if container is not None and not needs_replacing(container):
        _set_phase("running")
        return

    with _lock:
        if _state["phase"] in BUSY_PHASES:
            return

        _state.update(phase="starting", code="", detail="", progress=None)

    threading.Thread(target=_run, name="hd-browser-start", daemon=True).start()


def _remove_proxy(client):
    proxy = _existing(client, PROXY_CONTAINER_NAME)

    if proxy is not None:
        _remove(proxy)


def stop():
    try:
        client = _client()
        container = _existing(client)

        if container is not None:
            _remove(container, graceful=True)

        _remove_proxy(client)
    except docker.errors.DockerException as e:
        _set_phase("error", "docker_error", readable(e))
        return

    _set_phase("stopped")


def needs_replacing(container):
    """True when a running browser is on an older image than the one this HomeDock pins, and the newer one can be had: it is already here, or a pull has not just failed."""

    # Image IDs, not names: an engine may rewrite the name a container was created from (podman adds "localhost/").
    try:
        wanted = _client().images.get(_engine.image_reference())
    except docker.errors.ImageNotFound:
        return _pull_failed_at["at"] is None or time.monotonic() - _pull_failed_at["at"] > PULL_RETRY_SECONDS
    except docker.errors.DockerException:
        return False

    return container.attrs.get("Image") != wanted.id


def running_container():
    try:
        container = _existing(_client())

        return container if container is not None and container.status == "running" else None
    except docker.errors.DockerException:
        return None


def downloading():
    """True while Chromium is writing a download (it keeps a .crdownload file until done). If that cannot be checked, the answer is True, so a download is never cut off by a guess."""

    try:
        container = _existing(_client())

        if container is None or container.status != "running":
            return False

        # Only a file touched in the last 10 minutes counts: a leftover from an interrupted download must not block the idle stop forever.
        result = container.exec_run(["sh", "-c", f'test -n "$(find {_engine.download_dir} -maxdepth 1 -name \'*.crdownload\' -mmin -10 2>/dev/null)"'])

        return result.exit_code == 0
    except Exception:
        return True


def status():
    """{available, phase, code, detail, capabilities}. A browser that kept running across a HomeDock restart reports running."""

    if not docker_available():
        return {"available": False, "phase": "unavailable", "code": "docker_unavailable", "detail": "", "capabilities": {}}

    with _lock:
        snapshot = dict(_state)

    if snapshot["phase"] not in BUSY_PHASES and snapshot["phase"] != "error":
        snapshot["phase"] = "running" if upstream() else "stopped"

    return {"available": True, **snapshot, "capabilities": dict(_engine.capabilities)}

"""
hd_BrowserRuntime.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import json
import os
import threading
import time
import urllib.request

import docker

from pymodules.hd_BrowserEngine import CHROMIUM_USER, INIT_CAPABILITIES, PROXY_PORT, SANDBOX_PROBE, EgressProxyImage, SelkiesChromiumEngine
from pymodules.hd_ClassDockerClientManager import DockerClientManager
from pymodules.hd_FunctionsGlobals import running_OS
from pymodules.hd_FunctionsHostSelector import is_docker
from pymodules.hd_HomedockNetwork import connect_container, own_container

BROWSER_LABEL = "homedock.browser"

CONTAINER_NAME = "homedock-browser"
NETWORK_NAME = "homedock_browser"
EGRESS_NETWORK_NAME = "homedock_browser_egress"
PROXY_CONTAINER_NAME = "homedock-browser-proxy"
PROFILE_VOLUME = "homedock_browser_profile"

PROXY_MEMORY_LIMIT = "128m"
PROXY_PIDS_LIMIT = 128
PROXY_NANO_CPUS = 500_000_000
PROXY_START_TIMEOUT = 20

SECCOMP_PROFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hd_BrowserSeccomp.json")

MEMORY_LIMIT = "2g"
SHM_SIZE = "1g"
PIDS_LIMIT = 512
NANO_CPUS = 1_000_000_000

START_TIMEOUT = 90
POLL_INTERVAL = 1

BUSY_PHASES = ("pulling", "building", "checking", "starting")

_engine = SelkiesChromiumEngine()
_proxy_image = EgressProxyImage(os.path.join(os.path.dirname(os.path.abspath(__file__)), "hd_BrowserEgressProxy.py"))

_state = {"phase": "stopped", "code": "", "detail": ""}
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
        _state.update(phase=phase, code=code, detail=detail)


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
    """Fixed hardening. Nothing here is editable from the UI."""

    return {
        "cap_drop": ["ALL"],
        "cap_add": list(INIT_CAPABILITIES),
        "security_opt": ["no-new-privileges", f"seccomp={seccomp_profile()}"],
        "mem_limit": MEMORY_LIMIT,
        "memswap_limit": MEMORY_LIMIT,
        "pids_limit": PIDS_LIMIT,
        "nano_cpus": NANO_CPUS,
        "shm_size": SHM_SIZE,
        "privileged": False,
    }


def check_sandbox(client):
    """Refuses to start unless an unprivileged process in the container can create the namespaces Chromium's sandbox uses. There is no --no-sandbox fallback."""

    image = _engine.image_reference()

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

    _proxy_image.ensure_image(client, progress=lambda phase: _set_phase(phase))

    egress = _ensure_egress_network(client)

    stale = _existing(client, PROXY_CONTAINER_NAME)

    if stale is not None:
        _remove(stale)

    proxy = client.containers.create(
        _proxy_image.image_reference(),
        name=PROXY_CONTAINER_NAME,
        detach=True,
        network=egress.name,
        labels={BROWSER_LABEL: "1"},
        restart_policy={"Name": "no"},
        **_proxy_hardening(),
    )

    try:
        internal_network.connect(proxy, aliases=[PROXY_CONTAINER_NAME])
        proxy.start()
        _wait_proxy(proxy)
    except Exception:
        _remove(proxy)
        raise


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


def _remove(container):
    try:
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

    _engine.ensure_image(client, progress=lambda phase: _set_phase(phase))

    _set_phase("checking")
    check_sandbox(client)

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
        _remove(stale)

    container = client.containers.create(
        _engine.image_reference(),
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


def _run():
    try:
        _launch()
    except BrowserError as e:
        _set_phase("error", e.code, e.detail)
        return
    except docker.errors.DockerException as e:
        _set_phase("error", "docker_error", str(e))
        return
    except Exception as e:
        _set_phase("error", "unexpected", str(e))
        return

    _set_phase("running")


def start():
    """Starts the browser in the background. A second call while it is starting or running does nothing."""

    with _lock:
        if _state["phase"] in BUSY_PHASES:
            return

        if _state["phase"] == "running" and upstream():
            return

        _state.update(phase="starting", code="", detail="")

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
            _remove(container)

        _remove_proxy(client)
    except docker.errors.DockerException as e:
        _set_phase("error", "docker_error", str(e))
        return

    _set_phase("stopped")


def status():
    """{available, phase, code, detail, capabilities}. A browser that kept running across a HomeDock restart reports running."""

    if not docker_available():
        return {"available": False, "phase": "unavailable", "code": "docker_unavailable", "detail": "", "capabilities": {}}

    with _lock:
        snapshot = dict(_state)

    if snapshot["phase"] not in BUSY_PHASES and snapshot["phase"] != "error":
        snapshot["phase"] = "running" if upstream() else "stopped"

    return {"available": True, **snapshot, "capabilities": dict(_engine.capabilities)}

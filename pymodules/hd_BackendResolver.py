"""
hd_BackendResolver.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import glob
import os
import threading

import yaml

from pymodules.hd_DomainStore import ensure_app, get_app
from pymodules.hd_FunctionsGlobals import compose_upload_folder, running_OS
from pymodules.hd_FunctionsHostSelector import is_docker, docker_host
from pymodules.hd_PortDiscovery import published_port
from pymodules.hd_RuntimeCompose import web_ports_for

compose_folder = compose_upload_folder

_lock = threading.Lock()

_cache = {"signature": None, "index": {}}


def reset_cache():
    with _lock:
        _cache["signature"] = None
        _cache["index"] = {}


def _signature():
    try:
        return tuple((path, os.stat(path).st_mtime_ns) for path in sorted(glob.glob(os.path.join(compose_folder, "*.yml"))))
    except OSError:
        return ()


def _index():
    """{container name: {file, service, services}} for every installed compose file, rebuilt when the folder changes."""

    with _lock:
        signature = _signature()

        if _cache["signature"] == signature:
            return _cache["index"]

        index = {}

        for path, _ in signature:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    services = (yaml.safe_load(f) or {}).get("services") or {}
            except (OSError, yaml.YAMLError):
                continue

            for key, definition in services.items():
                if isinstance(definition, dict):
                    index[definition.get("container_name") or key] = {"file": path, "service": key, "services": services}

        _cache["signature"] = signature
        _cache["index"] = index

        return index


def sync_installed_apps():
    """Gives every installed container a store entry, and so a window slug."""

    for container in _index():
        if get_app(container) is None:
            ensure_app(container)


def installed_containers():
    return list(_index())


def compose_file_for(container):
    info = _index().get(container)

    return info["file"] if info else None


def web_port(container):
    info = _index().get(container)

    if info is None:
        app = get_app(container)

        return app["web_port"] if app else None

    return web_ports_for(info["file"], info["services"]).get(info["service"])


def _definition(container):
    info = _index().get(container)

    return info["services"][info["service"]] if info else {}


def container_ports(container):
    """The container-side ports the compose file declares (published or exposed), sorted, for choosing a domain's target."""

    found = set()

    for entry in list(_definition(container).get("ports") or []) + list(_definition(container).get("expose") or []):
        if isinstance(entry, dict):
            value = entry.get("target")
        else:
            value = str(entry).split("/")[0].split(":")[-1]

        try:
            found.add(int(value))
        except (TypeError, ValueError):
            continue

    return sorted(found)


def resolve_backend(container, port):
    """(host, port) to dial for a container's internal port, or None when it cannot be reached right now.

    Containerised HomeDock reaches apps by name over the shared network. A native one dials the loopback port Docker
    published; it never guesses, since the same number on localhost may be some other program.
    """

    if _definition(container).get("network_mode") == "host":
        return docker_host, port

    if is_docker:
        return container, port

    host_port = published_port(container, port)

    return (docker_host, host_port) if host_port else None


def reachability(container):
    """(reachable, reason). Host-network apps live on Docker Desktop's VM, which a native HomeDock cannot dial."""

    if _definition(container).get("network_mode") == "host" and not is_docker and running_OS != "Linux":
        return False, "Host-network apps are not reachable on this platform."

    return True, ""


def container_running(container):
    from pymodules.hd_ClassDockerClientManager import DockerClientManager

    try:
        return DockerClientManager.get_instance().get_client().containers.get(container).status == "running"
    except Exception:
        return False

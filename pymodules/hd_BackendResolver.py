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
from pymodules.hd_FunctionsGlobals import compose_upload_folder
from pymodules.hd_FunctionsHostSelector import is_docker, docker_host
from pymodules.hd_RuntimeCompose import parse_port_entry, web_ports_for

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


def resolve_backend(container, port):
    """(host, port) to dial for a container's internal port."""

    info = _index().get(container)
    definition = info["services"][info["service"]] if info else {}

    if definition.get("network_mode") == "host":
        return docker_host, port

    if is_docker:
        return container, port

    # Replaced by the loopback-only publishing of native installs
    for entry in definition.get("ports") or []:
        parsed = parse_port_entry(entry)

        if parsed and parsed["protocol"] == "tcp" and parsed["target"] == port and parsed["published"]:
            return docker_host, parsed["published"]

    return docker_host, port


def container_running(container):
    from pymodules.hd_ClassDockerClientManager import DockerClientManager

    try:
        return DockerClientManager.get_instance().get_client().containers.get(container).status == "running"
    except Exception:
        return False

"""
hd_RuntimeCompose.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import contextlib
import copy
import os
import re
import tempfile

import yaml

from pymodules.hd_FunctionsHostSelector import is_docker

NETWORK = "homedock_network"

_DIGITS = re.compile(r"\d+")


def parse_port_entry(entry):
    """Returns {target, published, protocol} for a compose ports entry, or None when it is a range or has no readable container port."""

    if isinstance(entry, dict):
        target = entry.get("target")
        published = entry.get("published")

        if not isinstance(target, int):
            return None

        return {"target": target, "published": int(published) if str(published or "").isdigit() else None, "protocol": entry.get("protocol", "tcp")}

    if isinstance(entry, int):
        return {"target": entry, "published": None, "protocol": "tcp"}

    if not isinstance(entry, str):
        return None

    spec, _, protocol = entry.partition("/")
    parts = spec.split(":")
    target = parts[-1].strip()

    if not _DIGITS.fullmatch(target):
        return None

    published = parts[-2].strip() if len(parts) >= 2 else ""

    return {"target": int(target), "published": int(published) if _DIGITS.fullmatch(published) else None, "protocol": protocol or "tcp"}


def primary_web_port(services, suggested=None):
    """The (service, container port) a window opens: the one matching the suggested port, else the first TCP port."""

    candidates = []

    for name, service in services.items():
        for entry in service.get("ports") or []:
            parsed = parse_port_entry(entry)

            if parsed and parsed["protocol"] == "tcp":
                candidates.append((name, parsed))

    if suggested is not None:
        for name, parsed in candidates:
            if suggested in (parsed["published"], parsed["target"]):
                return name, parsed["target"]

    if candidates:
        name, parsed = candidates[0]
        return name, parsed["target"]

    return None


def _strip_ports(service, targets):
    kept = []

    for entry in service.get("ports") or []:
        parsed = parse_port_entry(entry)

        if parsed and parsed["protocol"] == "tcp" and parsed["target"] in targets:
            continue

        kept.append(entry)

    if kept:
        service["ports"] = kept
    else:
        service.pop("ports", None)


def _join_network(service):
    networks = service.get("networks")

    if networks is None:
        service["networks"] = ["default", NETWORK]
    elif isinstance(networks, dict):
        networks.setdefault(NETWORK, {})
    elif NETWORK not in networks:
        networks.append(NETWORK)


def build_runtime_compose(compose, proxied):
    """Copy of the compose file with proxied HTTP ports unpublished and their services on the shared network.

    proxied maps a service name to the container ports HomeDock reaches over the network.
    """

    result = copy.deepcopy(compose)
    services = result.get("services") or {}
    joined = False

    for name, targets in proxied.items():
        service = services.get(name)

        if not targets or not isinstance(service, dict) or service.get("network_mode"):
            continue

        _strip_ports(service, targets)
        _join_network(service)
        joined = True

    declared = isinstance(result.get("networks"), dict) and NETWORK in result["networks"]

    if joined or declared:
        networks = result.get("networks")

        if not isinstance(networks, dict):
            networks = result["networks"] = {}

        networks[NETWORK] = {"external": True}

    return result


def project_name_for(compose_file):
    """Compose derives the project from the folder holding the file; keep that when the copy lives elsewhere."""

    return re.sub(r"[^a-z0-9_-]", "", os.path.basename(os.path.dirname(os.path.abspath(compose_file))).lower()).lstrip("_-")


def suggested_port_for(names):
    from pymodules.hd_DockerAPIContainerData import load_suggested_ports

    suggested_ports = load_suggested_ports()

    return next((suggested_ports[n] for n in names if n in suggested_ports), None)


def web_ports_for(compose_file, services):
    """{service: container port} of each service's window port: a saved override, else the app's primary port on its owning service."""

    from pymodules.hd_DomainStore import get_app

    ports = {}

    for name, service in services.items():
        app = get_app(service.get("container_name") or name) if isinstance(service, dict) else None

        if app and app.get("web_port"):
            ports[name] = app["web_port"]

    if ports:
        return ports

    names = [os.path.splitext(os.path.basename(compose_file))[0]] + [s.get("container_name") for s in services.values() if isinstance(s, dict)]
    primary = primary_web_port(services, suggested_port_for(names))

    return {primary[0]: primary[1]} if primary else {}


def proxied_ports_for(compose_file, services):
    """Container ports HomeDock reaches over the network instead of publishing: window ports and domain-assigned ports."""

    from pymodules.hd_DomainStore import get_app

    proxied = {name: {port} for name, port in web_ports_for(compose_file, services).items()}

    for name, service in services.items():
        app = get_app(service.get("container_name") or name) if isinstance(service, dict) else None

        for domain in (app or {}).get("domains", []):
            proxied.setdefault(name, set()).add(domain["port"])

    return proxied


@contextlib.contextmanager
def runtime_compose_file(compose_file):
    """Yields (file to run, project name, project directory). The user's file is run as is unless HomeDock is containerised."""

    project_name = project_name_for(compose_file)
    project_dir = os.path.dirname(os.path.abspath(compose_file))

    if not is_docker:
        yield compose_file, project_name, project_dir
        return

    try:
        with open(compose_file, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        runtime = build_runtime_compose(compose, proxied_ports_for(compose_file, compose.get("services") or {}))
    except Exception as e:
        print(f"Warning: could not build the runtime compose for {compose_file}, using it as written: {e}")
        yield compose_file, project_name, project_dir
        return

    with tempfile.TemporaryDirectory(prefix="hd_runtime_") as folder:
        path = os.path.join(folder, os.path.basename(compose_file))

        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(runtime, f, sort_keys=False)

        yield path, project_name, project_dir

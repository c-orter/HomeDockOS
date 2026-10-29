"""
hd_ComposeWarnings.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import yaml

DOCKER_SOCKETS = ("/var/run/docker.sock", "/run/docker.sock")


def _volume_sources(service: dict):
    for volume in service.get("volumes") or []:
        if isinstance(volume, str):
            yield volume.split(":", 1)[0].rstrip("/") or "/"
        elif isinstance(volume, dict) and volume.get("source"):
            yield str(volume["source"]).rstrip("/") or "/"


def compose_warnings(compose_text: str) -> list:
    """Security-relevant settings a user should see before installing: 'privileged', 'docker_socket', 'host_root'."""

    try:
        safe = compose_text.replace("[[", "__DBLBRK__").replace("]]", "__DBLBRK_END__")
        data = yaml.safe_load(safe)
    except (yaml.YAMLError, AttributeError):
        return []

    services = data.get("services") if isinstance(data, dict) else None
    found = set()

    for service in (services or {}).values():
        if not isinstance(service, dict):
            continue

        if service.get("privileged") is True:
            found.add("privileged")

        for source in _volume_sources(service):
            if source in DOCKER_SOCKETS:
                found.add("docker_socket")
            elif source == "/":
                found.add("host_root")

    return [code for code in ("privileged", "docker_socket", "host_root") if code in found]

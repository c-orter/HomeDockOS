"""
hd_HomedockNetwork.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import glob
import os
import socket

import docker
import yaml

from pymodules.hd_RuntimeCompose import NETWORK

OWN_CONTAINER_NAME = "homedock-os"


def ensure_network(client):
    found = client.networks.list(names=[NETWORK])
    found = [n for n in found if n.name == NETWORK]

    return found[0] if found else client.networks.create(NETWORK, driver="bridge")


def _connect(network, container):
    try:
        network.connect(container)
    except docker.errors.APIError as e:
        message = str(e).lower()

        # Docker says "already exists in network", Podman "already connected"
        if "already exists" not in message and "already connected" not in message:
            raise


def join_self(client):
    """Puts the HomeDock container itself on the shared network. Its hostname is its container id; the compose name is the fallback."""

    network = ensure_network(client)

    for ref in (socket.gethostname(), OWN_CONTAINER_NAME):
        try:
            container = client.containers.get(ref)
        except docker.errors.NotFound:
            continue

        _connect(network, container)

        return True

    return False


def connect_apps(client, compose_folder):
    """One pass over installed apps so ones started before this feature are reachable by name too."""

    network = ensure_network(client)

    for path in sorted(glob.glob(os.path.join(compose_folder, "*.yml"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                services = (yaml.safe_load(f) or {}).get("services") or {}
        except (OSError, yaml.YAMLError):
            continue

        for key, service in services.items():
            if not isinstance(service, dict) or service.get("network_mode"):
                continue

            try:
                container = client.containers.get(service.get("container_name") or key)
            except docker.errors.NotFound:
                continue

            _connect(network, container)


def setup_homedock_network(compose_folder):
    from pymodules.hd_ClassDockerClientManager import DockerClientManager

    try:
        client = DockerClientManager.get_instance().get_client()

        if not join_self(client):
            print(f" ! Could not find the HomeDock container to join {NETWORK}")

        connect_apps(client, compose_folder)
    except Exception as e:
        print(f" ! Could not set up the {NETWORK} network: {e}")

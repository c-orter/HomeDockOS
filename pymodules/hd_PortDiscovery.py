"""
hd_PortDiscovery.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import threading
import time

import docker

_lock = threading.Lock()

_cache = {}


def reset():
    with _lock:
        _cache.clear()


def extract_ports(attrs):
    """{container port: host port} for TCP ports Docker published."""

    ports = {}

    for key, bindings in ((attrs.get("NetworkSettings") or {}).get("Ports") or {}).items():
        target, _, protocol = key.partition("/")

        if protocol != "tcp" or not bindings or not target.isdigit():
            continue

        host_port = (bindings[0] or {}).get("HostPort")

        if host_port and host_port.isdigit():
            ports[int(target)] = int(host_port)

    return ports


def _client():
    from pymodules.hd_ClassDockerClientManager import DockerClientManager

    return DockerClientManager.get_instance().get_client()


def refresh(container, client=None):
    client = client or _client()

    try:
        found = client.containers.get(container)
        found.reload()
    except docker.errors.NotFound:
        forget(container)
        return {}

    ports = extract_ports(found.attrs)

    with _lock:
        _cache[container] = ports

    return ports


def forget(container):
    with _lock:
        _cache.pop(container, None)


def published_port(container, target, client=None):
    with _lock:
        cached = _cache.get(container)

    if cached is None or target not in cached:
        try:
            cached = refresh(container, client)
        except docker.errors.DockerException:
            return None

    return cached.get(target)


def watch_events(client, stop):
    """Keeps the cache current: a start event re-reads the container's ports, a die or destroy event forgets them."""

    for event in client.events(decode=True, filters={"type": "container", "event": ["start", "die", "destroy"]}):
        if stop.is_set():
            return

        name = ((event.get("Actor") or {}).get("Attributes") or {}).get("name")

        if not name:
            continue

        if event.get("Action") == "start":
            refresh(name, client)
        else:
            forget(name)


def start_port_events_thread():
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                watch_events(_client(), stop)
            except Exception as e:
                print(f" ! Docker event stream interrupted: {e}")

            time.sleep(5)

    threading.Thread(target=loop, daemon=True, name="hdos-port-events").start()

    return stop

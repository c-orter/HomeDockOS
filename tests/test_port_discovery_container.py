import shutil
import subprocess
import threading
import time
import uuid

import pytest
import requests

from pymodules import hd_PortDiscovery as discovery

pytestmark = pytest.mark.container

IMAGE = "docker.io/library/nginx:alpine"


@pytest.fixture
def engine():
    """A Docker-API socket for the local podman or docker, and a helper to run CLI commands against it."""

    docker_cli = shutil.which("docker")
    podman_cli = shutil.which("podman")

    if not (docker_cli or podman_cli):
        pytest.skip("needs podman or docker")

    cli = docker_cli or podman_cli
    service = None
    socket_path = None

    if not docker_cli:
        socket_path = f"/tmp/hd-pd-{uuid.uuid4().hex[:6]}.sock"
        service = subprocess.Popen([podman_cli, "system", "service", "--time=60", f"unix://{socket_path}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for _ in range(50):
            try:
                import os

                os.stat(socket_path)
                break
            except OSError:
                time.sleep(0.1)

    import docker

    client = docker.DockerClient(base_url=f"unix://{socket_path}") if socket_path else docker.from_env()

    yield {"cli": cli, "client": client}

    if service:
        service.terminate()


def test_loopback_port_is_discovered_and_follows_restarts(engine):
    client = engine["client"]
    name = f"hd-pd-{uuid.uuid4().hex[:6]}"
    discovery.reset()

    container = client.containers.run(IMAGE, name=name, detach=True, ports={"80/tcp": ("127.0.0.1", None)})

    try:
        port = discovery.published_port(name, 80, client)

        assert port

        for _ in range(30):
            try:
                assert "nginx" in requests.get(f"http://127.0.0.1:{port}/", timeout=1).text.lower()
                break
            except requests.RequestException:
                time.sleep(0.3)

        stop = threading.Event()
        thread = threading.Thread(target=discovery.watch_events, args=(client, stop), daemon=True)
        thread.start()
        time.sleep(1)

        container.stop(timeout=0)
        for _ in range(30):
            if name not in discovery._cache:
                break
            time.sleep(0.2)

        assert name not in discovery._cache

        container.start()
        for _ in range(30):
            if discovery._cache.get(name, {}).get(80):
                break
            time.sleep(0.2)

        assert discovery._cache[name][80]

        stop.set()
    finally:
        container.remove(force=True)
        discovery.reset()

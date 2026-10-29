import os
import shutil
import subprocess
import time
import uuid

import pytest

from pymodules import hd_HostShell as host
from pymodules import hd_UIContainerTerminal as terminal

pytestmark = pytest.mark.container

IMAGE = "docker.io/library/alpine:3"


@pytest.fixture
def engine(monkeypatch):
    docker_cli = shutil.which("docker")
    podman_cli = shutil.which("podman")

    if not (docker_cli or podman_cli):
        pytest.skip("needs podman or docker")

    service = None
    socket_path = None

    if not docker_cli:
        socket_path = f"/tmp/hd-hs-{uuid.uuid4().hex[:6]}.sock"
        service = subprocess.Popen([podman_cli, "system", "service", "--time=60", f"unix://{socket_path}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for _ in range(50):
            if os.path.exists(socket_path):
                break
            time.sleep(0.1)

    import docker

    client = docker.DockerClient(base_url=f"unix://{socket_path}") if socket_path else docker.from_env()
    monkeypatch.setattr(terminal, "_client", lambda: client)
    terminal._sessions.clear()

    yield client

    host.cleanup_helpers(client)

    if service:
        service.terminate()


def helpers(client):
    return client.containers.list(all=True, filters={"label": host.HELPER_LABEL})


def test_helper_is_privileged_in_the_host_pid_space_and_gone_after_close(engine, monkeypatch):
    # nsenter itself needs a rootful engine, so stand in a plain shell to exercise everything around it
    monkeypatch.setattr(host, "NSENTER_COMMAND", ["sh", "-c", "echo pid1=$(cat /proc/1/comm); exit 7"])
    session = terminal._make_session({"host": True, "kind": "docker", "image": IMAGE, "cols": 80, "rows": 24, "windows": False})

    session.open()

    try:
        found = helpers(engine)

        assert len(found) == 1
        assert found[0].attrs["HostConfig"]["Privileged"] is True
        assert found[0].attrs["HostConfig"]["PidMode"] == "host"
        assert found[0].attrs["HostConfig"]["NetworkMode"] in ("none", "private")

        output = b""
        deadline = time.time() + 15

        while time.time() < deadline:
            chunk = session.recv()

            if not chunk:
                break

            output += chunk

        # host pid space: pid 1 is the machine's init, not the helper's tail
        assert b"pid1=tail" not in output and b"pid1=" in output
        assert session.exit_code() == 7
    finally:
        session.close()

    session.removal.join(timeout=15)

    assert helpers(engine) == []
    assert terminal._active_host_count() == 0


def test_startup_cleanup_removes_helpers_a_crash_left_behind(engine):
    engine.containers.run(IMAGE, detach=True, entrypoint=["tail", "-f", "/dev/null"], labels={host.HELPER_LABEL: "1"})

    assert len(helpers(engine)) == 1

    host.cleanup_helpers(engine)

    assert helpers(engine) == []

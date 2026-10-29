import os
import shutil
import subprocess
import sys
import time
import uuid

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PEBBLE_IMAGE = os.environ.get("PEBBLE_IMAGE", "ghcr.io/letsencrypt/pebble:latest")
PEBBLE_CA_IN_IMAGE = "/test/certs/pebble.minica.pem"


def _container_runtime():
    return shutil.which("podman") or shutil.which("docker")


@pytest.fixture(scope="session")
def pebble(tmp_path_factory):
    """Starts a Pebble ACME test server; yields its directory URL, management URL and CA bundle path."""

    runtime = _container_runtime()
    if not runtime:
        pytest.skip("needs podman or docker to run Pebble")

    name = f"hd-pebble-{uuid.uuid4().hex[:8]}"
    run = subprocess.run(
        [
            runtime, "run", "-d", "--rm", "--name", name,
            "-p", "127.0.0.1::14000", "-p", "127.0.0.1::15000",
            "-e", "PEBBLE_VA_NOSLEEP=1",
            PEBBLE_IMAGE,
        ],
        capture_output=True, text=True,
    )
    if run.returncode != 0:
        pytest.skip(f"could not start Pebble: {run.stderr.strip()}")

    def host_port(container_port):
        out = subprocess.run([runtime, "port", name, str(container_port)], capture_output=True, text=True).stdout
        return out.strip().splitlines()[0].rsplit(":", 1)[1]

    try:
        ca_path = str(tmp_path_factory.mktemp("pebble") / "minica.pem")
        subprocess.run([runtime, "cp", f"{name}:{PEBBLE_CA_IN_IMAGE}", ca_path], check=True, capture_output=True)

        directory = f"https://localhost:{host_port(14000)}/dir"
        management = f"https://localhost:{host_port(15000)}"

        deadline = time.time() + 30
        while True:
            try:
                requests.get(directory, verify=ca_path, timeout=2).raise_for_status()
                break
            except requests.RequestException:
                if time.time() > deadline:
                    pytest.fail("Pebble did not become ready in 30s")
                time.sleep(0.5)

        yield {"directory": directory, "management": management, "ca": ca_path}
    finally:
        subprocess.run([runtime, "rm", "-f", name], capture_output=True)

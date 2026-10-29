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


def _run_pebble(tmp_path_factory, pebble_args=()):
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
            "--add-host", "hostbox:host-gateway",
            PEBBLE_IMAGE, *pebble_args,
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


@pytest.fixture(scope="session")
def pebble(tmp_path_factory):
    yield from _run_pebble(tmp_path_factory)


@pytest.fixture(scope="session")
def pebble_dns(tmp_path_factory):
    """Pebble that resolves through a TXT-only DNS server the test controls; yields the usual keys plus `records`."""

    import socket
    import struct
    import threading

    records = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    sock.settimeout(0.5)
    port = sock.getsockname()[1]
    stream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    stream.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    stream.bind(("0.0.0.0", port))
    stream.listen()
    stream.settimeout(0.5)
    stop = threading.Event()

    def answer(data):
        offset, labels = 12, []
        while data[offset]:
            labels.append(data[offset + 1 : offset + 1 + data[offset]].decode())
            offset += 1 + data[offset]
        question = data[12 : offset + 5]
        qtype = struct.unpack("!H", data[offset + 1 : offset + 3])[0]
        texts = records.get(".".join(labels).lower(), []) if qtype == 16 else []

        body = b""
        for text in texts:
            raw = text.encode()
            body += b"\xc0\x0c" + struct.pack("!HHIH", 16, 1, 1, len(raw) + 1) + bytes([len(raw)]) + raw

        return data[:2] + struct.pack("!HHHHH", 0x8400, 1, len(texts), 0, 0) + question + body

    def serve_udp():
        while not stop.is_set():
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            sock.sendto(answer(data), addr)

    def serve_one(connection):
        with connection:
            try:
                size = struct.unpack("!H", connection.recv(2))[0]
                reply = answer(connection.recv(size))
                connection.sendall(struct.pack("!H", len(reply)) + reply)
            except (OSError, struct.error):
                pass

    def serve_tcp():
        while not stop.is_set():
            try:
                connection, _ = stream.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=serve_one, args=(connection,), daemon=True).start()

    threading.Thread(target=serve_udp, daemon=True).start()
    threading.Thread(target=serve_tcp, daemon=True).start()

    try:
        for info in _run_pebble(tmp_path_factory, ("-dnsserver", f"hostbox:{port}")):
            yield {**info, "records": records}
    finally:
        stop.set()
        sock.close()
        stream.close()

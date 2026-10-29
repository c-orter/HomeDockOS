import asyncio
import shutil
import socket
import subprocess
import threading
import time
import uuid

import pytest
import requests

from pymodules import hd_AppSubdomains as subdomains
from pymodules import hd_BackendResolver as resolver
from pymodules import hd_DomainStore as store
from pymodules import hd_RuntimeCompose as runtime
from pymodules import hd_SubdomainRouter as router

pytestmark = pytest.mark.container

IMAGE = "docker.io/library/nginx:alpine"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def backend():
    runtime_bin = shutil.which("podman") or shutil.which("docker")

    if not runtime_bin:
        pytest.skip("needs podman or docker")

    port = free_port()
    name = f"hd-smoke-{uuid.uuid4().hex[:8]}"
    run = subprocess.run([runtime_bin, "run", "-d", "--rm", "--name", name, "-p", f"127.0.0.1:{port}:80", IMAGE], capture_output=True, text=True)

    if run.returncode != 0:
        pytest.skip(f"could not start the backend: {run.stderr.strip()}")

    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            requests.get(f"http://127.0.0.1:{port}/", timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.3)

    yield {"port": port, "stop": lambda: subprocess.run([runtime_bin, "stop", "-t", "0", name], capture_output=True)}

    subprocess.run([runtime_bin, "rm", "-f", name], capture_output=True)


@pytest.fixture
def proxy(tmp_path, monkeypatch, backend):
    from pymodules.hd_HDOSWebServerInit import homedock_www
    from pymodules.hd_SubdomainAuth import mint_app_token

    folder = tmp_path / "compose-link"
    folder.mkdir()
    (folder / "web.yml").write_text("services:\n  web:\n    container_name: web\n    ports: ['80']\n")

    homedock_www.config["SECRET_KEY"] = "smoke-test-secret"
    monkeypatch.setattr(resolver, "compose_folder", str(folder))
    monkeypatch.setattr(resolver, "is_docker", False)
    monkeypatch.setattr(resolver, "docker_host", "127.0.0.1")
    monkeypatch.setattr(resolver, "published_port", lambda container, target: backend["port"])
    monkeypatch.setattr(store, "domains_file", str(tmp_path / "domains.json"))
    monkeypatch.setattr(runtime, "suggested_port_for", lambda names: None)
    monkeypatch.setattr(subdomains, "get_desktop_hosts", lambda: {"dock.test", "localhost"})
    monkeypatch.setattr(store, "reserved_hosts", lambda: {"dock.test", "localhost"})
    monkeypatch.setattr(router, "_reverse_proxy_enabled", lambda: False)
    store.reset_cache()
    resolver.reset_cache()

    async def dashboard(scope, receive, send):
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"dashboard"})

    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    port = free_port()
    config = Config()
    config.bind = [f"127.0.0.1:{port}"]
    holder = {}

    def run():
        loop = asyncio.new_event_loop()
        holder["loop"] = loop
        holder["stop"] = asyncio.Event()
        loop.run_until_complete(serve(router.wrap_asgi_with_subdomain_router(dashboard), config, shutdown_trigger=holder["stop"].wait))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            requests.get(f"http://127.0.0.1:{port}/", timeout=0.5)
            break
        except requests.RequestException:
            time.sleep(0.1)

    yield {"url": f"http://127.0.0.1:{port}/", "cookie": {router.TOKEN_COOKIE_NAME: mint_app_token("web")}, "port": port}

    holder["loop"].call_soon_threadsafe(holder["stop"].set)
    thread.join(timeout=5)


def get(proxy, host, cookie=True, **kwargs):
    return requests.get(proxy["url"], headers={"Host": host, **kwargs.pop("headers", {})}, cookies=proxy["cookie"] if cookie else None, timeout=10, allow_redirects=False, **kwargs)


def test_stored_domain_reaches_the_real_backend(proxy):
    store.add_domain("web", "web.other.test", 80)

    response = get(proxy, "web.other.test")

    assert response.status_code == 200
    assert "Welcome to nginx" in response.text


def test_window_route_reaches_the_backend_without_any_domain(proxy):
    response = get(proxy, "web.dock.test")

    assert response.status_code == 200
    assert "Welcome to nginx" in response.text


def test_gated_domain_without_a_token_is_refused_not_redirected(proxy):
    store.add_domain("web", "web.other.test", 80)

    response = get(proxy, "web.other.test", cookie=False, headers={"Sec-Fetch-Dest": "document"})

    assert response.status_code == 403


def test_unknown_hosts_fall_through_and_the_namespace_gets_a_404(proxy):
    assert get(proxy, "elsewhere.org").text == "dashboard"
    assert get(proxy, "nothing.dock.test").status_code == 404


def test_stopped_app_answers_502(proxy, backend):
    store.add_domain("web", "web.other.test", 80)
    backend["stop"]()

    response = get(proxy, "web.other.test")

    assert response.status_code == 502
    assert "not running" in response.text.lower()

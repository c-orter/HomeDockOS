import asyncio
import json
from types import SimpleNamespace

import docker
import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestServer
from flask import Flask
from flask_login import LoginManager

from pymodules import hd_BrowserEngine as engine_module
from pymodules import hd_BrowserRuntime as runtime
from pymodules import hd_BrowserSettings as settings
from pymodules import hd_UIBrowser as browser


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "BROWSER_FOLDER", str(tmp_path / "_browser"))
    monkeypatch.setattr(settings, "SETTINGS_FILE", str(tmp_path / "_browser" / "settings.json"))
    browser.revoke_tickets()
    runtime._probed.clear()
    runtime._state.update(phase="stopped", code="", detail="")
    monkeypatch.setattr(runtime, "_read_sysctl", lambda name: None)


# tickets


def test_ticket_expires_when_not_renewed(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(browser.time, "monotonic", lambda: clock[0])

    ticket = browser.issue_ticket("admin", "10.0.0.2")

    assert browser.ticket_alive(ticket)

    clock[0] += browser.TICKET_TTL + 1

    assert not browser.ticket_alive(ticket)
    assert browser.renew_ticket(ticket) is None


def test_renewing_keeps_a_ticket_alive(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(browser.time, "monotonic", lambda: clock[0])

    ticket = browser.issue_ticket("admin", "10.0.0.2")

    for _ in range(5):
        clock[0] += browser.TICKET_TTL - 5
        assert browser.renew_ticket(ticket) is not None

    assert browser.ticket_alive(ticket)


def test_unknown_and_empty_tickets_never_validate():
    assert browser.renew_ticket("") is None
    assert browser.renew_ticket(None) is None
    assert browser.renew_ticket("x" * 43) is None
    assert not browser.ticket_alive("x" * 43)


def test_tickets_are_unguessable_and_unique():
    tickets = {browser.issue_ticket("admin", "ip") for _ in range(50)}

    assert len(tickets) == 50
    assert all(len(t) >= 40 for t in tickets)


# session api


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    LoginManager(app).user_loader(lambda user_id: None)
    app.add_url_rule("/status", "status", browser.api_browser_status)
    app.add_url_rule("/session", "session", browser.api_browser_session, methods=["POST"])
    app.add_url_rule("/renew", "renew", browser.api_browser_session_renew, methods=["POST"])
    app.add_url_rule("/stop", "stop", browser.api_browser_stop, methods=["POST"])
    monkeypatch.setattr(runtime, "docker_available", lambda: True)
    monkeypatch.setattr(runtime, "upstream", lambda: ("browser", 3000))

    return app.test_client()


def test_session_needs_a_running_browser(client, monkeypatch):
    monkeypatch.setattr(runtime, "upstream", lambda: None)

    response = client.post("/session")

    assert response.status_code == 409
    assert response.get_json()["code"] == "not_running"


def test_session_mints_a_ticket_in_the_path(client):
    data = client.post("/session").get_json()

    assert data["path"] == f"/browser/{data['ticket']}/"
    assert data["ttl"] == browser.TICKET_TTL
    assert browser.ticket_alive(data["ticket"])


def test_renew_endpoint_reports_expiry(client):
    ticket = client.post("/session").get_json()["ticket"]

    assert client.post("/renew", json={"ticket": ticket}).get_json()["success"]
    assert client.post("/renew", json={"ticket": "nope"}).status_code == 404
    assert client.post("/renew", json={}).status_code == 404


def test_stopping_revokes_every_ticket(client, monkeypatch):
    monkeypatch.setattr(runtime, "stop", lambda: runtime._state.update(phase="stopped"))
    ticket = client.post("/session").get_json()["ticket"]

    client.post("/stop")

    assert not browser.ticket_alive(ticket)


# relay


def scope_for(path, method="GET", headers=(), kind="http", query=b""):
    return {"type": kind, "method": method, "path": path, "query_string": query, "headers": [(k.encode(), v.encode()) for k, v in headers], "scheme": "http"}


async def call_http(app, scope, body=b""):
    queue = [{"type": "http.request", "body": body, "more_body": False}]
    sent = []

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)

    start = next(m for m in sent if m["type"] == "http.response.start")
    payload = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")

    return start["status"], {k.decode(): v.decode() for k, v in start["headers"]}, payload


async def downstream_marker(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"downstream"})


relay = browser.wrap_asgi_with_browser(downstream_marker)


def test_other_paths_go_downstream():
    status, _, body = asyncio.run(call_http(relay, scope_for("/api/other")))

    assert (status, body) == (200, b"downstream")


def test_relay_rejects_a_bad_ticket():
    status, _, _ = asyncio.run(call_http(relay, scope_for("/browser/" + "a" * 43 + "/index.html")))

    assert status == 403


def test_relay_rejects_a_malformed_ticket():
    status, _, _ = asyncio.run(call_http(relay, scope_for("/browser/short/")))

    assert status == 404


def test_relay_rejects_an_expired_ticket(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(browser.time, "monotonic", lambda: clock[0])
    ticket = browser.issue_ticket("admin", "ip")
    clock[0] += browser.TICKET_TTL + 1

    status, _, _ = asyncio.run(call_http(relay, scope_for(f"/browser/{ticket}/")))

    assert status == 403


def test_relay_rejects_another_sites_origin():
    ticket = browser.issue_ticket("admin", "ip")

    status, _, _ = asyncio.run(call_http(relay, scope_for(f"/browser/{ticket}/", headers=[("host", "dash.example"), ("origin", "https://evil.example")])))

    assert status == 403


def test_relay_redirects_so_relative_addresses_stay_under_the_ticket():
    ticket = browser.issue_ticket("admin", "ip")

    status, headers, _ = asyncio.run(call_http(relay, scope_for(f"/browser/{ticket}")))

    assert status == 308
    assert headers["location"] == f"/browser/{ticket}/"


def test_relay_says_so_when_the_browser_is_not_running(monkeypatch):
    monkeypatch.setattr(runtime, "upstream", lambda: None)
    ticket = browser.issue_ticket("admin", "ip")

    status, _, _ = asyncio.run(call_http(relay, scope_for(f"/browser/{ticket}/")))

    assert status == 503


async def with_upstream(routes, work):
    app = web.Application()

    for method, path, handler in routes:
        app.router.add_route(method, path, handler)

    server = TestServer(app)
    await server.start_server()

    try:
        await work((server.host, server.port))
    finally:
        await server.close()


def test_relay_forwards_with_sandbox_cors_and_without_cookies(monkeypatch):
    seen = {}

    async def index(request):
        seen["cookie"] = request.headers.get("Cookie")
        seen["authorization"] = request.headers.get("Authorization")
        seen["path"] = request.path_qs
        response = web.Response(text="<html>client</html>", content_type="text/html")
        response.set_cookie("leak", "1")
        response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
        return response

    async def work(address):
        monkeypatch.setattr(runtime, "upstream", lambda: address)
        ticket = browser.issue_ticket("admin", "ip")
        headers = [("host", "dash.example"), ("origin", "null"), ("cookie", "homedock_session=secret"), ("authorization", "Bearer x")]

        status, out, body = await call_http(relay, scope_for(f"/browser/{ticket}/index.html", headers=headers, query=b"a=1"))

        assert status == 200
        assert body == browser._inject_shim(b"<html>client</html>")
        assert b"localStorage" in body and body.endswith(b"client</html>")
        assert out["content-security-policy"] == browser.SANDBOX_POLICY
        assert "allow-same-origin" not in out["content-security-policy"]
        assert out["access-control-allow-origin"] == "null"
        assert out["access-control-allow-credentials"] == "true"
        assert "set-cookie" not in out
        assert seen == {"cookie": None, "authorization": None, "path": "/index.html?a=1"}

    asyncio.run(with_upstream([("GET", "/index.html", index)], work))


def test_every_relayed_response_may_be_embedded_in_a_require_corp_desktop(monkeypatch):
    """HomeDock's desktop is served with COEP require-corp, which blocks any frame (and any file it loads) whose response does not opt in."""

    async def upstream_page(request):
        return web.Response(text="data", content_type="text/plain", headers={"Cross-Origin-Resource-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "unsafe-none"})

    async def work(address):
        monkeypatch.setattr(runtime, "upstream", lambda: address)
        displaced = browser.issue_ticket("admin", "ip")
        ticket = browser.issue_ticket("admin", "ip")

        for path in (f"/browser/{ticket}/", f"/browser/{ticket}/app.js", f"/browser/{'a' * 43}/x", f"/browser/{displaced}/x"):
            _, out, _ = await call_http(relay, scope_for(path, headers=[("host", "dash.example"), ("origin", "null")]))

            assert out["cross-origin-embedder-policy"] == "require-corp", path
            assert out["cross-origin-resource-policy"] == "cross-origin", path

    asyncio.run(with_upstream([("GET", "/", upstream_page), ("GET", "/app.js", upstream_page)], work))


def test_the_storage_shim_goes_in_ahead_of_the_clients_scripts():
    page = browser._inject_shim(b'<html><head><meta charset="utf-8"><script src="a.js"></script></head></html>')

    assert page.index(b"localStorage") < page.index(b"a.js")
    assert browser._inject_shim(b"<p>no head</p>").startswith(b"<script>")


def test_the_audio_shim_starts_muted_and_listens_only_to_the_parent_page():
    page = browser._inject_shim(b"<html><head></head></html>")
    shim = browser._AUDIO_SHIM.decode()

    assert browser._AUDIO_SHIM in page and page.index(b"hd-audio") < page.index(b"</head>")
    assert "muted=true" in shim
    assert "e.source!==parent" in shim
    assert 'd.type!=="hd-audio"' in shim


def test_relay_answers_a_cors_preflight_only_for_a_live_ticket(monkeypatch):
    async def work(address):
        monkeypatch.setattr(runtime, "upstream", lambda: address)
        ticket = browser.issue_ticket("admin", "ip")
        headers = [("host", "dash.example"), ("origin", "null"), ("access-control-request-headers", "x-test")]

        status, out, _ = await call_http(relay, scope_for(f"/browser/{ticket}/x", method="OPTIONS", headers=headers))
        bad, _, _ = await call_http(relay, scope_for("/browser/" + "b" * 43 + "/x", method="OPTIONS", headers=headers))

        assert status == 204
        assert out["access-control-allow-origin"] == "null"
        assert out["access-control-allow-headers"] == "x-test"
        assert bad == 403

    asyncio.run(with_upstream([], work))


def test_relay_carries_a_websocket_through(monkeypatch):
    async def echo(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        async for message in ws:
            if message.type == WSMsgType.TEXT:
                await ws.send_str("echo:" + message.data)

        return ws

    async def work(address):
        monkeypatch.setattr(runtime, "upstream", lambda: address)
        ticket = browser.issue_ticket("admin", "ip")
        incoming = asyncio.Queue()
        sent = []

        await incoming.put({"type": "websocket.connect"})
        await incoming.put({"type": "websocket.receive", "text": "hi"})

        async def receive():
            return await incoming.get()

        async def send(message):
            sent.append(message)

            if message["type"] == "websocket.send":
                await incoming.put({"type": "websocket.disconnect", "code": 1000})

        scope = scope_for(f"/browser/{ticket}/api/websockets", kind="websocket", headers=[("origin", "null")])
        await asyncio.wait_for(relay(scope, receive, send), 5)

        assert sent[0]["type"] == "websocket.accept"
        assert {"type": "websocket.send", "text": "echo:hi"} in sent

    asyncio.run(with_upstream([("GET", "/api/websockets", echo)], work))


def test_relay_refuses_a_websocket_without_a_ticket():
    async def go():
        sent = []
        incoming = [{"type": "websocket.connect"}]

        async def receive():
            return incoming.pop(0)

        async def send(message):
            sent.append(message)

        await relay(scope_for("/browser/" + "c" * 43 + "/api/websockets", kind="websocket"), receive, send)

        return sent

    sent = asyncio.run(go())

    assert sent == [{"type": "websocket.close", "code": 4403}]


# hardening and refuse-to-start


class FakeContainers:
    def __init__(self, probe_error=None):
        self.probe_error = probe_error
        self.created = []
        self.probes = []
        self.items = {}

    def run(self, image, **kwargs):
        self.probes.append((image, kwargs))

        if self.probe_error:
            raise self.probe_error

    def create(self, image, **kwargs):
        self.created.append((image, kwargs))
        container = SimpleNamespace(status="running", attrs={"NetworkSettings": {"Networks": {runtime.NETWORK_NAME: {"IPAddress": "172.30.0.2"}}}}, start=lambda: None, stop=lambda timeout=10: None, reload=lambda: None, remove=lambda force=False: None)
        self.items[kwargs["name"]] = container

        return container

    def get(self, name):
        if name not in self.items:
            raise docker.errors.NotFound("no such container")

        return self.items[name]


class FakeNetworks:
    def __init__(self, internal=None):
        self.items = {}
        self.created = []
        self.connected = []

        if internal is not None:
            self.items[runtime.NETWORK_NAME] = self._make(runtime.NETWORK_NAME, internal)

    def _make(self, name, internal):
        return SimpleNamespace(name=name, attrs={"Internal": internal}, connect=lambda container, **kw: self.connected.append((name, container, kw)))

    def list(self, names=None):
        return [n for k, n in self.items.items() if not names or k in names]

    def create(self, name, **kwargs):
        self.created.append((name, kwargs))
        self.items[name] = self._make(name, kwargs.get("internal", False))

        return self.items[name]


def fake_client(probe_error=None, networks=None):
    volumes = SimpleNamespace(get=lambda name: (_ for _ in ()).throw(docker.errors.NotFound("x")), create=lambda name, **kw: None)

    return SimpleNamespace(containers=FakeContainers(probe_error), networks=networks or FakeNetworks(), volumes=volumes, images=SimpleNamespace(get=lambda ref: object()))


def container_error():
    return docker.errors.ContainerError(None, 1, "unshare", "image", b"unshare: unshare failed: Operation not permitted")


def test_start_is_refused_when_the_sandbox_cannot_be_enabled(monkeypatch):
    client = fake_client(probe_error=container_error())
    monkeypatch.setattr(runtime, "_client", lambda: client)
    monkeypatch.setattr(runtime, "_reachable_from_here", lambda: True)
    monkeypatch.setattr(runtime, "_read_sysctl", lambda name: "1" if name == "kernel/apparmor_restrict_unprivileged_userns" else None)

    runtime._run()

    state = runtime._state

    assert state["phase"] == "error"
    assert state["code"] == "sandbox_unavailable"
    assert "AppArmor" in state["detail"]
    assert client.containers.created == []


def test_a_blocked_sandbox_is_never_worked_around(monkeypatch):
    client = fake_client(probe_error=container_error())
    monkeypatch.setattr(runtime, "_client", lambda: client)
    monkeypatch.setattr(runtime, "_reachable_from_here", lambda: True)

    runtime._run()
    runtime._run()

    assert client.containers.created == []
    assert all("unconfined" not in " ".join(kw["security_opt"]) for _, kw in client.containers.probes)


def test_the_probe_runs_as_chromium_does_under_the_same_hardening(monkeypatch):
    client = fake_client()

    runtime.check_sandbox(client)

    image, kwargs = client.containers.probes[0]

    assert image == runtime.engine().image_reference()
    assert kwargs["entrypoint"] == engine_module.SANDBOX_PROBE
    assert kwargs["user"] == engine_module.CHROMIUM_USER
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["network_mode"] == "none"
    assert any(opt.startswith("seccomp=") for opt in kwargs["security_opt"])


def test_a_good_probe_is_remembered(monkeypatch):
    client = fake_client()

    runtime.check_sandbox(client)
    runtime.check_sandbox(client)

    assert len(client.containers.probes) == 1


def test_the_cause_names_the_ubuntu_restriction(monkeypatch):
    monkeypatch.setattr(runtime, "_read_sysctl", lambda name: "1" if name == "kernel/apparmor_restrict_unprivileged_userns" else None)

    assert "apparmor_restrict_unprivileged_userns" in runtime.sandbox_cause()


def test_the_container_is_created_with_the_fixed_spec(monkeypatch):
    client = fake_client()
    monkeypatch.setattr(runtime, "_client", lambda: client)
    monkeypatch.setattr(runtime, "_reachable_from_here", lambda: True)
    monkeypatch.setattr(runtime, "is_docker", False)
    monkeypatch.setattr(runtime, "_wait_ready", lambda container: None)

    runtime._run()

    assert runtime._state["phase"] == "running"

    image, kwargs = next(c for c in client.containers.created if c[1]["name"] == runtime.CONTAINER_NAME)

    assert image == runtime.engine().image_reference()
    assert "@sha256:" in runtime.engine().base_reference()
    assert kwargs["cap_drop"] == ["ALL"]
    assert set(kwargs["cap_add"]) == set(engine_module.INIT_CAPABILITIES)
    assert "no-new-privileges" in kwargs["security_opt"]
    assert any(opt.startswith("seccomp=") and "unconfined" not in opt for opt in kwargs["security_opt"])
    assert kwargs["privileged"] is False
    assert kwargs["pids_limit"] == 512
    assert kwargs["mem_limit"] == "2048m" and kwargs["shm_size"] == "1024m" and kwargs["nano_cpus"] == 1_000_000_000
    assert kwargs["network"] == runtime.NETWORK_NAME
    assert "ports" not in kwargs
    assert "network_mode" not in kwargs
    assert all("docker.sock" not in str(bind) for bind in kwargs["volumes"]) and set(kwargs["volumes"]) == {runtime.PROFILE_VOLUME}
    assert kwargs["labels"] == {runtime.BROWSER_LABEL: "1"}
    assert client.networks.created[0][1]["internal"] is True


def launch(monkeypatch):
    client = fake_client()
    monkeypatch.setattr(runtime, "_client", lambda: client)
    monkeypatch.setattr(runtime, "_reachable_from_here", lambda: True)
    monkeypatch.setattr(runtime, "is_docker", False)
    monkeypatch.setattr(runtime, "_wait_ready", lambda container: None)
    runtime._run()

    return client


def test_the_browser_is_pointed_at_the_proxy_and_nothing_else(monkeypatch):
    client = launch(monkeypatch)
    _, browser_kwargs = next(c for c in client.containers.created if c[1]["name"] == runtime.CONTAINER_NAME)
    flags = browser_kwargs["environment"]["CHROME_CLI"].split(" ")

    assert f"--proxy-server=http://{runtime.PROXY_CONTAINER_NAME}:{runtime.PROXY_PORT}" in flags
    assert "--proxy-bypass-list=<-loopback>" in flags
    assert "--disable-quic" in flags
    assert browser_kwargs["network"] == runtime.NETWORK_NAME


def test_only_the_proxy_touches_the_network_that_reaches_the_internet(monkeypatch):
    client = launch(monkeypatch)
    names = {n: kw for n, kw in client.networks.created}

    assert names[runtime.NETWORK_NAME]["internal"] is True
    assert not names[runtime.EGRESS_NETWORK_NAME].get("internal")

    proxy_image, proxy_kwargs = next(c for c in client.containers.created if c[1]["name"] == runtime.PROXY_CONTAINER_NAME)
    _, browser_kwargs = next(c for c in client.containers.created if c[1]["name"] == runtime.CONTAINER_NAME)

    assert proxy_kwargs["network"] == runtime.EGRESS_NETWORK_NAME
    assert browser_kwargs["network"] != runtime.EGRESS_NETWORK_NAME
    assert [(n, kw["aliases"]) for n, _, kw in client.networks.connected] == [(runtime.NETWORK_NAME, [runtime.PROXY_CONTAINER_NAME])]


def test_the_proxy_container_is_locked_down(monkeypatch):
    client = launch(monkeypatch)
    _, kwargs = next(c for c in client.containers.created if c[1]["name"] == runtime.PROXY_CONTAINER_NAME)

    assert kwargs["cap_drop"] == ["ALL"] and "cap_add" not in kwargs
    assert kwargs["read_only"] is True
    assert kwargs["privileged"] is False
    assert "no-new-privileges" in kwargs["security_opt"]
    assert "volumes" not in kwargs and "ports" not in kwargs
    assert kwargs["labels"] == {runtime.BROWSER_LABEL: "1"}


def test_stopping_removes_the_proxy_with_the_browser(monkeypatch):
    client = launch(monkeypatch)
    removed = []

    for name, c in client.containers.items.items():
        c.remove = lambda force=False, n=name: removed.append(n)

    runtime.stop()

    assert set(removed) == {runtime.CONTAINER_NAME, runtime.PROXY_CONTAINER_NAME}


def test_the_browser_is_asked_to_stop_before_it_is_removed_so_chromium_can_save_its_session(monkeypatch):
    order = []
    container = SimpleNamespace(status="running", stop=lambda timeout=10: order.append(("stop", timeout)), remove=lambda force=False: order.append(("remove", force)))

    runtime._remove(container, graceful=True)

    assert order == [("stop", runtime.STOP_GRACE_SECONDS), ("remove", True)]

    order.clear()
    runtime._remove(container)

    assert order == [("remove", True)]


def test_a_browser_that_will_not_stop_politely_is_still_removed():
    def refuses(timeout=10):
        raise docker.errors.APIError("could not stop")

    removed = []
    container = SimpleNamespace(status="running", stop=refuses, remove=lambda force=False: removed.append(force))

    runtime._remove(container, graceful=True)

    assert removed == [True]


def test_chromium_is_told_not_to_ask_about_the_last_session():
    flags = runtime.engine().proxy_flags("proxy:3128")

    assert "--disable-session-crashed-bubble" in flags and "--hide-crash-restore-bubble" in flags


def test_the_proxy_image_is_pinned_and_rebuilds_when_the_script_changes(tmp_path):
    script = tmp_path / "p.py"
    script.write_text("one")
    image = engine_module.EgressProxyImage(str(script))
    first = image.image_reference()

    assert "@sha256:" in image.base_reference()
    assert image.image_reference() == first

    script.write_text("two")

    assert image.image_reference() != first


def test_the_browser_network_is_internal(monkeypatch):
    networks = FakeNetworks()
    client = fake_client(networks=networks)

    runtime._ensure_network(client)

    assert networks.created == [(runtime.NETWORK_NAME, {"driver": "bridge", "internal": True, "labels": {runtime.BROWSER_LABEL: "1"}})]


def test_an_existing_network_that_is_not_internal_is_refused():
    networks = FakeNetworks(internal=False)

    with pytest.raises(runtime.BrowserError) as refused:
        runtime._ensure_network(fake_client(networks=networks))

    assert refused.value.code == "network_unsafe"


def test_the_engine_never_ships_no_sandbox():
    dockerfile = engine_module._DERIVED_DOCKERFILE.format(base=runtime.engine().base_reference())

    assert "sed -i '/--no-sandbox/d'" in dockerfile
    assert "! grep -q -- --no-sandbox" in dockerfile
    assert dockerfile.startswith(f"FROM {engine_module.SELKIES_BASE_REPOSITORY}@sha256:")


def test_the_image_is_pinned_by_digest_not_tag():
    reference = runtime.engine().base_reference()

    assert "@sha256:" in reference
    assert ":latest" not in reference
    assert len(engine_module.SELKIES_BASE_DIGEST) == len("sha256:") + 64


def test_the_seccomp_profile_adds_only_the_namespace_calls():
    profile = json.loads(runtime.seccomp_profile())

    assert profile["defaultAction"] == "SCMP_ACT_ERRNO"

    def allowed_unconditionally(name):
        return any(name in rule["names"] and rule["action"] == "SCMP_ACT_ALLOW" and not any(k in rule for k in ("includes", "excludes", "args")) for rule in profile["syscalls"])

    for name in ("unshare", "setns", "clone", "clone3", "chroot"):
        assert allowed_unconditionally(name), name

    for name in ("mount", "umount2", "pivot_root", "reboot", "kexec_load", "init_module", "bpf"):
        assert not allowed_unconditionally(name), name

    assert not any(rule["action"] == "SCMP_ACT_ERRNO" and "clone3" in rule["names"] for rule in profile["syscalls"])
    assert "unconfined" not in runtime.seccomp_profile()


def test_status_reports_unavailable_without_docker(monkeypatch):
    monkeypatch.setattr(runtime, "docker_available", lambda: False)

    assert runtime.status()["available"] is False
    assert runtime.status()["phase"] == "unavailable"


# sessions, take-over, idle stop


def test_a_newer_ticket_displaces_the_older_one():
    first = browser.issue_ticket("admin", "ip")
    second = browser.issue_ticket("admin", "ip")

    assert not browser.ticket_live(first)
    assert browser.ticket_live(second)
    assert browser.ticket_alive(first)


def test_taking_back_displaces_the_window_that_took_over():
    first = browser.issue_ticket("admin", "ip")
    second = browser.issue_ticket("admin", "ip")
    third = browser.issue_ticket("admin", "ip")

    assert [browser.ticket_live(t) for t in (first, second, third)] == [False, False, True]


def test_a_displaced_window_still_counts_as_open_until_it_closes():
    first = browser.issue_ticket("admin", "ip")
    browser.issue_ticket("admin", "ip")

    assert browser.open_sessions() == 2

    browser.release_ticket(first)

    assert browser.open_sessions() == 1


def test_a_window_that_stops_renewing_stops_counting(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(browser.time, "monotonic", lambda: clock[0])
    browser.issue_ticket("admin", "ip")
    clock[0] += browser.TICKET_TTL + 1

    assert browser.open_sessions() == 0


def test_renewing_a_displaced_ticket_says_so_and_keeps_it_counting(client):
    first = client.post("/session").get_json()["ticket"]
    client.post("/session")

    response = client.post("/renew", json={"ticket": first})

    assert response.status_code == 409
    assert response.get_json()["code"] == "displaced"
    assert browser.ticket_alive(first)


def test_closing_a_window_releases_only_its_ticket(client, monkeypatch):
    app = client.application
    app.add_url_rule("/close", "close", browser.api_browser_session_close, methods=["POST"])
    first = client.post("/session").get_json()["ticket"]
    second = client.post("/session").get_json()["ticket"]

    client.post("/close", json={"ticket": second})

    assert not browser.ticket_alive(second)
    assert browser.ticket_alive(first)


def test_the_relay_turns_a_displaced_ticket_away():
    first = browser.issue_ticket("admin", "ip")
    browser.issue_ticket("admin", "ip")

    status, _, _ = asyncio.run(call_http(relay, scope_for(f"/browser/{first}/index.html")))

    assert status == 409


def test_the_relay_closes_a_displaced_websocket():
    first = browser.issue_ticket("admin", "ip")
    browser.issue_ticket("admin", "ip")

    async def go():
        sent = []
        incoming = [{"type": "websocket.connect"}]

        async def receive():
            return incoming.pop(0)

        async def send(message):
            sent.append(message)

        await relay(scope_for(f"/browser/{first}/api/websockets", kind="websocket"), receive, send)

        return sent

    assert asyncio.run(go()) == [{"type": "websocket.close", "code": 4409}]


@pytest.fixture
def idle(monkeypatch):
    stopped = []
    monkeypatch.setattr(runtime, "status", lambda: {"phase": "running"})
    monkeypatch.setattr(runtime, "stop", lambda: stopped.append(True))
    monkeypatch.setattr(runtime, "downloading", lambda: False)
    monkeypatch.setattr(browser, "idle_timeout_seconds", lambda: 900)
    browser._idle["since"] = None

    return stopped


def test_the_browser_stops_after_the_idle_timeout_with_no_windows(idle):
    assert browser.idle_tick(now=0) is False
    assert browser.idle_tick(now=899) is False
    assert browser.idle_tick(now=900) is True
    assert idle == [True]


def test_an_open_window_keeps_the_browser_running(idle):
    browser.issue_ticket("admin", "ip")

    for now in (0, 5000, 100000):
        assert browser.idle_tick(now=now) is False

    assert idle == []


def test_closing_the_last_window_restarts_the_idle_clock(idle):
    ticket = browser.issue_ticket("admin", "ip")
    browser.idle_tick(now=0)
    browser.release_ticket(ticket)

    assert browser.idle_tick(now=1000) is False
    assert browser.idle_tick(now=1899) is False
    assert browser.idle_tick(now=1900) is True


def test_a_download_in_progress_is_never_cut_off(idle, monkeypatch):
    monkeypatch.setattr(runtime, "downloading", lambda: True)
    browser.idle_tick(now=0)

    assert browser.idle_tick(now=5000) is False
    assert idle == []

    monkeypatch.setattr(runtime, "downloading", lambda: False)

    assert browser.idle_tick(now=5001) is True


def test_a_stopped_browser_has_nothing_to_stop(idle, monkeypatch):
    monkeypatch.setattr(runtime, "status", lambda: {"phase": "stopped"})

    assert browser.idle_tick(now=0) is False
    assert browser.idle_tick(now=99999) is False
    assert idle == []


def test_the_download_guard_looks_for_unfinished_downloads(monkeypatch):
    commands = []
    running = SimpleNamespace(status="running", exec_run=lambda cmd: commands.append(cmd) or SimpleNamespace(exit_code=0))
    monkeypatch.setattr(runtime, "_client", lambda: SimpleNamespace(containers=SimpleNamespace(get=lambda name: running)))

    assert runtime.downloading() is True
    assert ".crdownload" in commands[0][-1] and runtime.engine().download_dir in commands[0][-1]

    running.exec_run = lambda cmd: SimpleNamespace(exit_code=1)

    assert runtime.downloading() is False


def test_the_download_guard_assumes_a_download_when_it_cannot_tell(monkeypatch):
    def broken():
        raise docker.errors.DockerException("daemon went away")

    monkeypatch.setattr(runtime, "_client", broken)

    assert runtime.downloading() is True


def test_the_idle_timeout_defaults_to_fifteen_minutes_and_follows_settings():
    assert browser.idle_timeout_seconds() == 15 * 60

    settings.save({"idle_minutes": 45})

    assert browser.idle_timeout_seconds() == 45 * 60

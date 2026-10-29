import asyncio
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin, login_user

from pymodules import hd_AppSubdomains as subdomains
from pymodules import hd_BackendResolver as resolver
from pymodules import hd_DomainAccess as access
from pymodules import hd_DomainStore as store
from pymodules import hd_RuntimeCompose as runtime
from pymodules import hd_SubdomainAuth as auth
from pymodules import hd_SubdomainRouter as router
from pymodules import hd_UIDomains as api
from pymodules.hd_HDOSWebServerInit import homedock_www

SECRET = "domain-access-secret"


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    folder = tmp_path / "compose-link"
    folder.mkdir()
    (folder / "web.yml").write_text("services:\n  web:\n    container_name: web\n    ports: ['8080:80']\n")
    (folder / "db.yml").write_text("services:\n  db:\n    container_name: db\n    ports: ['5432']\n")

    homedock_www.config["SECRET_KEY"] = SECRET
    monkeypatch.setattr(resolver, "compose_folder", str(folder))
    monkeypatch.setattr(store, "domains_file", str(tmp_path / "domains.json"))
    monkeypatch.setattr(store, "reserved_hosts", lambda: {"dock.test", "homedock.local"})
    monkeypatch.setattr(runtime, "suggested_port_for", lambda names: None)
    monkeypatch.setattr(subdomains, "get_desktop_hosts", lambda: {"dock.test", "homedock.local", "localhost"})
    monkeypatch.setattr(router, "get_desktop_hosts", subdomains.get_desktop_hosts)
    monkeypatch.setattr(access, "read_config", lambda: {"base_domain": "dock.test"})
    store.reset_cache()
    resolver.reset_cache()


# ---- tokens ----


def test_token_opens_only_its_container_and_host():
    token = auth.mint_app_token("web", "web.a.test")

    assert auth.verify_app_token(token, "web", "web.a.test", 60)
    assert not auth.verify_app_token(token, "web", "web.b.test", 60)
    assert not auth.verify_app_token(token, "db", "web.a.test", 60)


def test_token_expires_and_garbage_is_rejected():
    token = auth.mint_app_token("web", "web.a.test")

    assert not auth.verify_app_token(token, "web", "web.a.test", -1)
    assert not auth.verify_app_token("junk", "web", "web.a.test", 60)
    assert not auth.verify_app_token(None, "web", "web.a.test", 60)


# ---- return validation ----


@pytest.mark.parametrize(
    "raw",
    [
        "https://evil.example/",
        "https://web.a.test@evil.example/",
        "https://evil.example\\@web.a.test/",
        "//web.a.test/",
        "javascript:alert(1)",
        "https://web.a.test:notaport/",
        "https://web.a.test//evil.example",
        "https://web.a.test/\r\nSet-Cookie: x=1",
        "",
        None,
    ],
)
def test_return_to_anything_but_a_stored_domain_is_refused(raw):
    store.add_domain("web", "web.a.test", 80)

    assert auth.parse_return_target(raw) is None


def test_return_to_a_stored_domain_is_rebuilt_from_parts():
    store.add_domain("web", "web.a.test", 80)

    assert auth.parse_return_target("https://WEB.a.test:8443/deep/path?x=1#frag") == ("web", "web.a.test", "https://web.a.test:8443/deep/path?x=1")
    assert auth.parse_return_target("http://web.a.test")[2] == "http://web.a.test/"


def test_the_window_address_is_not_a_return_target():
    assert auth.parse_return_target("https://web.dock.test/") is None


# ---- /app-auth ----


class _User(UserMixin):
    id = "owner"


@pytest.fixture
def dashboard():
    app = Flask(__name__)
    app.config.update(SECRET_KEY=SECRET, TESTING=True)
    manager = LoginManager(app)
    manager.user_loader(lambda user_id: _User())
    app.add_url_rule("/login", "login_page", lambda: "login page")
    app.add_url_rule("/app-auth", "app_auth", auth.app_auth)

    @app.route("/sign-in")
    def sign_in():
        login_user(_User())
        return "ok"

    return app


def test_signed_out_visitor_is_sent_to_login_and_the_return_is_remembered(dashboard):
    store.add_domain("web", "web.a.test", 80)
    client = dashboard.test_client()

    response = client.get("/app-auth?return=https%3A%2F%2Fweb.a.test%2Fx")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    with client.session_transaction() as session:
        assert session["post_login_return"].startswith("/app-auth?return=")


def test_signed_in_visitor_is_sent_back_with_a_token_for_that_domain_only(dashboard):
    store.add_domain("web", "web.a.test", 80)
    client = dashboard.test_client()
    client.get("/sign-in")

    response = client.get("/app-auth?return=https%3A%2F%2Fweb.a.test%3A8443%2Fx%3Fq%3D1")
    location = urlsplit(response.headers["Location"])
    query = parse_qs(location.query)

    assert response.status_code == 302
    assert (location.scheme, location.netloc, location.path) == ("https", "web.a.test:8443", "/x")
    assert query["q"] == ["1"]
    assert auth.verify_app_token(query["__hd_token"][0], "web", "web.a.test", 60)
    assert not auth.verify_app_token(query["__hd_token"][0], "web", "elsewhere.test", 60)
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_signed_in_visitor_is_not_redirected_to_an_unknown_host(dashboard):
    client = dashboard.test_client()
    client.get("/sign-in")

    response = client.get("/app-auth?return=https%3A%2F%2Fevil.example%2F")

    assert response.status_code == 400
    assert "Location" not in response.headers


# ---- direct mode ----


def test_cert_name_matching():
    assert access.cert_covers_name("web.a.test", ["web.a.test"])
    assert access.cert_covers_name("web.a.test", ["*.a.test"])
    assert not access.cert_covers_name("x.web.a.test", ["*.a.test"])
    assert not access.cert_covers_name("a.test", ["*.a.test"])
    assert not access.cert_covers_name("web.b.test", ["*.a.test"])


def covered(monkeypatch, domains, self_signed=False, enabled=True):
    monkeypatch.setattr(access, "ssl_enabled", lambda: enabled)
    monkeypatch.setattr(access, "get_cert_domains_and_type", lambda: {"domains": domains, "is_self_signed": self_signed})


def test_direct_is_refused_with_a_reason_until_there_is_a_covering_cert(monkeypatch):
    covered(monkeypatch, [], enabled=False)
    assert "no certificate" in access.direct_refusal("web.a.test")

    covered(monkeypatch, ["*.a.test"], self_signed=True)
    assert "self-signed" in access.direct_refusal("web.a.test")

    covered(monkeypatch, ["*.other.test"])
    assert "does not cover web.a.test" in access.direct_refusal("web.a.test")

    covered(monkeypatch, ["*.a.test"])
    assert access.direct_refusal("web.a.test") is None


@pytest.mark.parametrize("fqdn", ["web.homedock.local", "web.homedock.localhost", "box.local"])
def test_direct_is_never_allowed_on_local_names(monkeypatch, fqdn):
    covered(monkeypatch, ["*.homedock.local", fqdn])

    assert "local" in access.direct_refusal(fqdn)


def test_is_direct_needs_https_a_direct_domain_and_a_covering_cert(monkeypatch):
    covered(monkeypatch, ["*.a.test"])
    app = {"implicit": False, "mode": "direct", "fqdn": "web.a.test"}

    assert access.is_direct(app, "https")
    assert not access.is_direct(app, "http")
    assert not access.is_direct({**app, "mode": "gated"}, "https")
    assert not access.is_direct({**app, "implicit": True}, "https")

    covered(monkeypatch, [])
    assert not access.is_direct(app, "https")


def test_dashboard_host(monkeypatch):
    assert access.dashboard_host_for("web.homedock.local") == "homedock.local"
    assert access.dashboard_host_for("web.a.test") == "dock.test"

    monkeypatch.setattr(access, "read_config", lambda: {"base_domain": ""})

    assert access.dashboard_host_for("web.a.test") is None
    assert access.dashboard_host_for("web.homedock.local") == "homedock.local"


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.add_url_rule("/api/domains", "list", api.api_domains)
    app.add_url_rule("/api/domains/add", "add", api.api_domains_add, methods=["POST"])
    app.add_url_rule("/api/domains/update", "update", api.api_domains_update, methods=["POST"])

    return app.test_client()


def test_api_refuses_direct_with_the_reason_and_accepts_it_once_covered(client, monkeypatch):
    covered(monkeypatch, [], enabled=False)

    refused = client.post("/api/domains/add", json={"container": "web", "fqdn": "web.a.test", "port": 80, "mode": "direct"})

    assert refused.status_code == 400
    assert "no certificate" in refused.get_json()["message"]

    client.post("/api/domains/add", json={"container": "web", "fqdn": "web.a.test", "port": 80})
    assert client.post("/api/domains/update", json={"container": "web", "fqdn": "web.a.test", "mode": "direct"}).status_code == 400

    covered(monkeypatch, ["*.a.test"])

    assert client.post("/api/domains/update", json={"container": "web", "fqdn": "web.a.test", "mode": "direct"}).status_code == 200
    assert store.get_app("web")["domains"][0]["mode"] == "direct"
    assert client.post("/api/domains/update", json={"container": "web", "fqdn": "web.a.test", "mode": "bogus"}).status_code == 400


def test_api_lists_why_each_domain_cannot_be_public(client, monkeypatch):
    covered(monkeypatch, [])
    client.post("/api/domains/add", json={"container": "web", "fqdn": "web.homedock.local", "port": 80})

    domain = client.get("/api/domains?container=web").get_json()["domains"][0]

    assert "local" in domain["direct_refusal"]


# ---- router flow ----


def run_router(scope, app, monkeypatch, scheme="https"):
    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b""}

    async def go():
        return await router._authorize(scope, send, app, scheme, scope_host(scope))

    allowed = asyncio.run(go())

    return allowed, sent


def scope_host(scope):
    return dict((k.decode(), v.decode()) for k, v in scope["headers"])["host"]


def http_scope(host, path="/", query=b"", document=True, cookie=None):
    headers = [(b"host", host.encode())]

    if document:
        headers.append((b"sec-fetch-dest", b"document"))

    if cookie:
        headers.append((b"cookie", f"{router.TOKEN_COOKIE_NAME}={cookie}".encode()))

    return {"type": "http", "method": "GET", "path": path, "raw_path": path.encode(), "query_string": query, "headers": headers}


def app_for(host):
    return subdomains.resolve_app_for_host(host)


def location_of(sent):
    return dict(sent[0]["headers"])[b"location"].decode()


def test_gated_document_request_is_sent_to_the_base_domain_dashboard(monkeypatch):
    store.add_domain("web", "web.a.test", 80)

    allowed, sent = run_router(http_scope("web.a.test", "/deep", b"x=1"), app_for("web.a.test"), monkeypatch)

    assert not allowed
    assert sent[0]["status"] == 302

    location = urlsplit(location_of(sent))

    assert (location.scheme, location.netloc, location.path) == ("https", "dock.test", "/app-auth")
    assert parse_qs(location.query)["return"] == ["https://web.a.test/deep?x=1"]
    assert auth.parse_return_target(parse_qs(location.query)["return"][0]) is not None


def test_dashboard_port_follows_the_request(monkeypatch):
    store.add_domain("web", "web.a.test", 80)

    _, sent = run_router(http_scope("web.a.test:8443"), app_for("web.a.test:8443"), monkeypatch)

    assert urlsplit(location_of(sent)).netloc == "dock.test:8443"


def test_lan_names_log_in_through_homedock_local(monkeypatch):
    store.add_domain("web", "web.homedock.local", 80)

    _, sent = run_router(http_scope("web.homedock.local"), app_for("web.homedock.local"), monkeypatch, scheme="http")

    assert urlsplit(location_of(sent)).netloc == "homedock.local"


def test_without_a_base_domain_the_explanation_page_shows(monkeypatch):
    monkeypatch.setattr(access, "read_config", lambda: {"base_domain": ""})
    store.add_domain("web", "web.a.test", 80)

    allowed, sent = run_router(http_scope("web.a.test"), app_for("web.a.test"), monkeypatch)

    assert not allowed
    assert sent[0]["status"] == 403
    assert b"base domain" in sent[1]["body"]
    assert dict(sent[0]["headers"])[b"content-type"].startswith(b"text/html")


def test_non_document_requests_get_a_plain_403(monkeypatch):
    store.add_domain("web", "web.a.test", 80)

    _, sent = run_router(http_scope("web.a.test", document=False), app_for("web.a.test"), monkeypatch)

    assert sent[0]["status"] == 403
    assert sent[1]["body"] == b"Not authorized."


def test_valid_handoff_token_becomes_a_host_only_cookie(monkeypatch):
    store.add_domain("web", "web.a.test", 80)
    token = auth.mint_app_token("web", "web.a.test")

    allowed, sent = run_router(http_scope("web.a.test", "/x", f"a=1&__hd_token={token}".encode()), app_for("web.a.test"), monkeypatch)
    headers = dict(sent[0]["headers"])

    assert not allowed
    assert headers[b"location"] == b"/x?a=1"
    assert b"HttpOnly" in headers[b"set-cookie"]
    assert b"Domain=" not in headers[b"set-cookie"]


def test_token_for_another_domain_is_not_honoured(monkeypatch):
    store.add_domain("web", "web.a.test", 80)
    store.add_domain("web", "web.b.test", 80)
    token = auth.mint_app_token("web", "web.b.test")

    allowed, sent = run_router(http_scope("web.a.test", query=f"__hd_token={token}".encode()), app_for("web.a.test"), monkeypatch)

    assert not allowed
    assert "app-auth" in location_of(sent)

    allowed, _ = run_router(http_scope("web.a.test", cookie=token), app_for("web.a.test"), monkeypatch)

    assert not allowed


def test_cookie_for_the_exact_host_lets_the_request_through(monkeypatch):
    store.add_domain("web", "web.a.test", 80)

    allowed, sent = run_router(http_scope("web.a.test", cookie=auth.mint_app_token("web", "web.a.test")), app_for("web.a.test"), monkeypatch)

    assert allowed and sent == []


def test_direct_domain_skips_the_login_only_over_https(monkeypatch):
    covered(monkeypatch, ["*.a.test"])
    store.add_domain("web", "web.a.test", 80)
    store.update_domain("web", "web.a.test", mode="direct")

    https_allowed, _ = run_router(http_scope("web.a.test"), app_for("web.a.test"), monkeypatch, scheme="https")
    http_allowed, _ = run_router(http_scope("web.a.test"), app_for("web.a.test"), monkeypatch, scheme="http")

    assert https_allowed
    assert not http_allowed


def test_window_route_unauthenticated_goes_to_the_dashboard_host(monkeypatch):
    _, sent = run_router(http_scope("web.dock.test"), app_for("web.dock.test"), monkeypatch)

    assert location_of(sent) == "https://dock.test/"


def test_window_token_binds_to_its_exact_host(monkeypatch):
    token = auth.mint_app_token("web", "web.dock.test")

    allowed, _ = run_router(http_scope("web.dock.test", cookie=token), app_for("web.dock.test"), monkeypatch)
    other, _ = run_router(http_scope("web.dock.test", cookie=auth.mint_app_token("web", "web.homedock.local")), app_for("web.dock.test"), monkeypatch)

    assert allowed and not other

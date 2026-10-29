import pytest
from flask import Flask

from pymodules import hd_UIAppLoader as loader
from pymodules.hd_DockerAPIContainerData import primary_domain_url


class FakeResponse:
    def __init__(self, status):
        self.status_code = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.add_url_rule("/api/check-app", "check", loader.check_app, methods=["POST"])
    monkeypatch.setattr(loader, "get_safe_hostname", lambda: "dock.test")

    return app.test_client()


def test_probes_the_resolved_backend_not_a_host_port(client, monkeypatch):
    seen = []

    def head(url, **kwargs):
        seen.append(url)
        return FakeResponse(200)

    monkeypatch.setattr(loader, "web_port", lambda container: 80)
    monkeypatch.setattr(loader, "resolve_backend", lambda container, port: ("web", 80))
    monkeypatch.setattr(loader.requests, "head", head)

    response = client.post("/api/check-app", json={"container": "web", "subpath": "a/b"})

    assert response.get_json() == {"available": True}
    assert seen == ["https://web:80/ab"]


def test_unknown_app_or_unresolved_backend(client, monkeypatch):
    monkeypatch.setattr(loader, "web_port", lambda container: None)

    assert client.post("/api/check-app", json={"container": "ghost"}).status_code == 404
    assert client.post("/api/check-app", json={}).status_code == 404

    monkeypatch.setattr(loader, "web_port", lambda container: 80)
    monkeypatch.setattr(loader, "resolve_backend", lambda container, port: None)

    assert client.post("/api/check-app", json={"container": "web"}).status_code == 404


def test_unreachable_backend_reports_unavailable(client, monkeypatch):
    def head(url, **kwargs):
        raise loader.requests.ConnectionError("down")

    monkeypatch.setattr(loader, "web_port", lambda container: 80)
    monkeypatch.setattr(loader, "resolve_backend", lambda container, port: ("web", 80))
    monkeypatch.setattr(loader.requests, "head", head)

    response = client.post("/api/check-app", json={"container": "web"})

    assert response.status_code == 404
    assert response.get_json() == {"available": False}


def test_primary_domain_url():
    domains = [{"fqdn": "a.example.com", "path": "/web"}, {"fqdn": "b.example.com", "path": ""}]

    assert primary_domain_url(domains, "https", ":8443") == "https://a.example.com:8443/web"
    assert primary_domain_url([], "https", "") is None

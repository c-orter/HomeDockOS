import pytest
from flask import Flask

from pymodules import hd_BackendResolver as resolver
from pymodules import hd_DomainStore as store
from pymodules import hd_RuntimeCompose as runtime
from pymodules import hd_UIDomains as api


@pytest.fixture
def client(tmp_path, monkeypatch):
    folder = tmp_path / "compose-link"
    folder.mkdir()
    (folder / "web.yml").write_text("services:\n  web:\n    container_name: web\n    ports: ['8080:80']\n")
    monkeypatch.setattr(resolver, "compose_folder", str(folder))
    monkeypatch.setattr(store, "domains_file", str(tmp_path / "domains.json"))
    monkeypatch.setattr(store, "reserved_hosts", lambda: {"homedock.local"})
    monkeypatch.setattr(runtime, "suggested_port_for", lambda names: None)
    store.reset_cache()
    resolver.reset_cache()

    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.add_url_rule("/api/domains", "list", api.api_domains)
    app.add_url_rule("/api/domains/add", "add", api.api_domains_add, methods=["POST"])
    app.add_url_rule("/api/domains/update", "update", api.api_domains_update, methods=["POST"])
    app.add_url_rule("/api/domains/remove", "remove", api.api_domains_remove, methods=["POST"])
    app.add_url_rule("/api/domains/web-port", "web", api.api_domains_web_port, methods=["POST"])

    return app.test_client()


def test_add_list_update_remove_roundtrip(client):
    assert client.post("/api/domains/add", json={"container": "web", "fqdn": "a.example.com", "port": 80}).status_code == 200
    assert client.post("/api/domains/add", json={"container": "web", "fqdn": "b.example.com", "port": 80}).status_code == 200

    listed = client.get("/api/domains?container=web").get_json()

    assert [d["fqdn"] for d in listed["domains"]] == ["a.example.com", "b.example.com"]
    assert listed["effective_web_port"] == 80

    client.post("/api/domains/update", json={"container": "web", "fqdn": "b.example.com", "primary": True, "port": 8080})

    assert client.get("/api/domains?container=web").get_json()["domains"][0] == {"fqdn": "b.example.com", "port": 8080, "protocol": "auto", "path": "", "mode": "gated"}

    assert client.post("/api/domains/remove", json={"container": "web", "fqdn": "a.example.com"}).status_code == 200
    assert len(client.get("/api/domains?container=web").get_json()["domains"]) == 1


def test_clash_returns_409_naming_the_owner(client):
    client.post("/api/domains/add", json={"container": "web", "fqdn": "a.example.com", "port": 80})
    store.ensure_app("other")

    response = client.post("/api/domains/add", json={"container": "other", "fqdn": "a.example.com", "port": 80})

    assert response.status_code == 409
    assert "web" in response.get_json()["message"]


def test_invalid_input_and_unknown_app(client):
    assert client.post("/api/domains/add", json={"container": "web", "fqdn": "10.0.0.1", "port": 80}).status_code == 400
    assert client.post("/api/domains/add", json={"container": "ghost", "fqdn": "a.example.com", "port": 80}).status_code == 404
    assert client.post("/api/domains/add", json={"container": "web", "fqdn": "a.example.com", "port": "x"}).status_code == 400


def test_web_port_override_roundtrip(client):
    response = client.post("/api/domains/web-port", json={"container": "web", "port": 9000})

    assert response.get_json()["web_port"] == 9000
    assert client.post("/api/domains/web-port", json={"container": "web", "port": None}).get_json()["web_port"] == 80

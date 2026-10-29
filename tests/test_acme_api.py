import pytest
from flask import Flask

from pymodules import hd_AcmeCredentials as credentials
from pymodules import hd_UIAcme as api


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials, "CREDENTIALS_FILE", str(tmp_path / "credentials.json"))
    monkeypatch.setattr(credentials, "read_config", lambda: {})
    monkeypatch.setattr(api, "read_config", lambda: {"base_domain": "home.example.com"})

    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.add_url_rule("/credentials", "add", api.api_acme_credentials, methods=["POST"])
    app.add_url_rule("/credentials/remove", "remove", api.api_acme_credentials_remove, methods=["POST"])
    app.add_url_rule("/reissue", "reissue", api.api_acme_reissue, methods=["POST"])

    return app.test_client()


def test_credentials_are_added_listed_without_tokens_and_removed(client):
    added = client.post("/credentials", json={"zone": "Example.com.", "provider": "cloudflare", "token": "secret"})

    assert added.status_code == 200
    assert added.get_json()["credentials"] == [{"zone": "example.com", "provider": "cloudflare"}]
    assert "secret" not in added.get_data(as_text=True)
    assert credentials.stored_token("example.com", "cloudflare") == "secret"

    removed = client.post("/credentials/remove", json={"zone": "example.com"})

    assert removed.status_code == 200 and removed.get_json()["credentials"] == []
    assert client.post("/credentials/remove", json={"zone": "example.com"}).status_code == 404


def test_an_empty_token_keeps_the_saved_one_but_needs_one_the_first_time(client):
    assert client.post("/credentials", json={"zone": "example.com", "provider": "cloudflare", "token": ""}).status_code == 400

    client.post("/credentials", json={"zone": "example.com", "provider": "cloudflare", "token": "secret"})

    assert client.post("/credentials", json={"zone": "example.com", "provider": "cloudflare", "token": ""}).status_code == 200
    assert credentials.stored_token("example.com", "cloudflare") == "secret"


def test_bad_zone_and_provider_are_refused(client):
    assert client.post("/credentials", json={"zone": "com", "provider": "cloudflare", "token": "x"}).status_code == 400
    assert client.post("/credentials", json={"zone": "example.com", "provider": "nope", "token": "x"}).status_code == 400


def test_reissue_needs_a_covering_credential_and_starts_a_run(client, monkeypatch):
    assert client.post("/reissue", json={}).status_code == 400

    client.post("/credentials", json={"zone": "example.com", "provider": "cloudflare", "token": "secret"})

    started = []
    monkeypatch.setattr(api, "claim", lambda staging=False: True)
    monkeypatch.setattr(api, "_start_worker", lambda domain, staging: started.append((domain, staging)) or True)

    response = client.post("/reissue", json={"staging": True})

    assert response.status_code == 202 and started == [("home.example.com", True)]


def test_reissue_refuses_while_a_request_runs(client, monkeypatch):
    client.post("/credentials", json={"zone": "example.com", "provider": "cloudflare", "token": "secret"})
    monkeypatch.setattr(api, "claim", lambda staging=False: False)

    assert client.post("/reissue", json={}).status_code == 409

from types import SimpleNamespace

import pytest
from flask import Flask

from pymodules import hd_UIContainerTerminal as terminal


class FakeContainers:
    def __init__(self, items):
        self.items = items

    def list(self, all=False):
        return self.items


@pytest.fixture
def client(monkeypatch):
    items = [SimpleNamespace(name="web", status="running"), SimpleNamespace(name="Db", status="exited"), SimpleNamespace(name="homedock-os", status="running")]
    fake = SimpleNamespace(containers=FakeContainers(items))
    monkeypatch.setattr(terminal, "_client", lambda: fake)
    monkeypatch.setattr(terminal, "is_docker", True)
    monkeypatch.setattr(terminal, "own_container", lambda c: items[2])

    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.add_url_rule("/targets", "targets", terminal.api_container_terminal_targets)

    return app.test_client()


def test_lists_every_container_and_names_the_homedock_one(client):
    data = client.get("/targets").get_json()

    assert data["homedock"] == "homedock-os"
    assert [c["name"] for c in data["containers"]] == ["Db", "homedock-os", "web"]
    assert data["containers"][0]["status"] == "exited"


def test_native_install_has_no_homedock_container(client, monkeypatch):
    monkeypatch.setattr(terminal, "is_docker", False)

    assert client.get("/targets").get_json()["homedock"] is None


def test_shell_in_homedock_own_container_needs_the_host_gates(client, monkeypatch):
    own = SimpleNamespace(id="own")
    other = SimpleNamespace(id="web")
    monkeypatch.setattr(terminal, "own_container", lambda c: own)

    terminal._require_gates_for_own_container(other, {}, "1.1.1.1")

    monkeypatch.setattr(terminal.host_shell, "host_shell_enabled", lambda: False)

    with pytest.raises(terminal.TerminalError) as off:
        terminal._require_gates_for_own_container(own, {"password": "x"}, "1.1.1.1")

    assert off.value.code == "host_disabled"

    calls = []
    monkeypatch.setattr(terminal.host_shell, "host_shell_enabled", lambda: True)
    monkeypatch.setattr(terminal.host_shell, "authorize", lambda ip, password, code: calls.append((ip, password, code)))

    terminal._require_gates_for_own_container(own, {"password": "pw", "code": "123456"}, "1.1.1.1")

    assert calls == [("1.1.1.1", "pw", "123456")]

    def refuse(ip, password, code):
        raise terminal.host_shell.HostShellError("auth_failed", 401)

    monkeypatch.setattr(terminal.host_shell, "authorize", refuse)

    with pytest.raises(terminal.TerminalError) as bad:
        terminal._require_gates_for_own_container(own, {}, "1.1.1.1")

    assert (bad.value.code, bad.value.status) == ("auth_failed", 401)

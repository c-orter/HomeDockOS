import asyncio
import time
from types import SimpleNamespace

import bcrypt
import pyotp
import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin, login_user

from pymodules import hd_HostShell as host
from pymodules import hd_UIContainerTerminal as terminal

PASSWORD = "correct horse"


class FakeSession:
    def __init__(self, entry):
        self.entry = entry


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    config = {"user_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()), "2fa_enabled": False, "host_shell_enabled": True}
    monkeypatch.setattr(host, "read_config", lambda: config)
    monkeypatch.setattr(terminal, "read_config", lambda: config)
    monkeypatch.setattr(host, "audit_file", str(tmp_path / "hostshell.log"))
    host._failures.clear()
    terminal._sessions.clear()
    terminal._tickets.clear()

    return config


# ---- authorization ----


def test_correct_password_passes():
    host.authorize("10.0.0.1", PASSWORD, "")


@pytest.mark.parametrize("password", ["wrong", "", None, 123])
def test_wrong_or_missing_password_is_refused(password):
    with pytest.raises(host.HostShellError) as error:
        host.authorize("10.0.0.1", password, "")

    assert error.value.code == "auth_failed"


def test_repeated_failures_lock_the_address_out_even_for_the_right_password():
    for _ in range(host.MAX_AUTH_FAILURES):
        with pytest.raises(host.HostShellError):
            host.authorize("10.0.0.1", "wrong", "")

    with pytest.raises(host.HostShellError) as error:
        host.authorize("10.0.0.1", PASSWORD, "")

    assert error.value.status == 429
    host.authorize("10.0.0.2", PASSWORD, "")


def test_2fa_code_is_required_when_enabled(isolated, monkeypatch):
    isolated.update({"2fa_enabled": True, "2fa_secret": pyotp.random_base32(), "2fa_backup_codes": "HDS-1,HDS-2"})
    saved = []
    monkeypatch.setattr(host, "save_backup_codes", saved.append)

    with pytest.raises(host.HostShellError):
        host.authorize("10.0.0.1", PASSWORD, "")

    with pytest.raises(host.HostShellError):
        host.authorize("10.0.0.1", PASSWORD, "000000")

    host.authorize("10.0.0.1", PASSWORD, "hds-1")

    assert saved == [["HDS-2"]]


def test_a_good_code_does_not_replace_the_password(isolated, monkeypatch):
    isolated.update({"2fa_enabled": True, "2fa_secret": pyotp.random_base32(), "2fa_backup_codes": "HDS-1"})
    monkeypatch.setattr(host, "save_backup_codes", lambda codes: None)

    with pytest.raises(host.HostShellError):
        host.authorize("10.0.0.1", "wrong", "HDS-1")


# ---- audit ----


def test_audit_records_who_and_when_and_survives_hostile_fields(tmp_path):
    host.audit("open", "10.0.0.1", "owner\n2099-01-01***open", "host", "docker")
    host.audit("close", "10.0.0.1", "owner", "host", "exited after 5s")

    entries = host.read_audit()

    assert [e["event"] for e in entries] == ["close", "open"]
    assert len(entries) == 2
    assert entries[1]["user"].count("***") == 0
    assert set(entries[0]) == {"timestamp", "event", "ip", "user", "target", "detail"}


# ---- endpoints ----


class _User(UserMixin):
    id = "owner"


@pytest.fixture
def client(monkeypatch):
    items = [SimpleNamespace(name="web", status="running")]
    fake = SimpleNamespace(containers=SimpleNamespace(list=lambda all=False: items), info=lambda: {"SecurityOptions": ["name=seccomp"]})
    monkeypatch.setattr(terminal, "_client", lambda: fake)
    monkeypatch.setattr(host, "_client", lambda: fake, raising=False)
    monkeypatch.setattr(terminal, "is_docker", False)

    app = Flask(__name__)
    app.config.update(SECRET_KEY="x", TESTING=True)
    manager = LoginManager(app)
    manager.user_loader(lambda uid: _User())
    app.add_url_rule("/targets", "targets", terminal.api_container_terminal_targets)
    app.add_url_rule("/session", "session", terminal.api_container_terminal_session, methods=["POST"])

    @app.route("/in")
    def sign_in():
        login_user(_User())
        return "ok"

    test_client = app.test_client()
    test_client.get("/in")

    return test_client


def test_host_target_is_absent_until_the_switch_is_on(client, isolated):
    isolated["host_shell_enabled"] = False

    assert client.get("/targets").get_json()["host"] is None

    isolated["host_shell_enabled"] = True

    assert client.get("/targets").get_json()["host"] == {"available": True, "reason": "", "requires_2fa": False}


def test_host_target_says_why_it_is_unavailable_on_rootless_docker(client, monkeypatch):
    own = SimpleNamespace(name="homedock-os")
    monkeypatch.setattr(terminal, "is_docker", True)
    monkeypatch.setattr(terminal, "own_container", lambda c: own)
    monkeypatch.setattr(host, "engine_is_rootless", lambda c: True)

    target = client.get("/targets").get_json()["host"]

    assert not target["available"]
    assert "rootless" in target["reason"]


def test_session_for_the_host_needs_the_switch(client, isolated):
    isolated["host_shell_enabled"] = False

    response = client.post("/session", json={"host": True, "password": PASSWORD})

    assert response.status_code == 403
    assert response.get_json()["code"] == "host_disabled"


def test_session_for_the_host_needs_the_fresh_password(client):
    assert client.post("/session", json={"host": True}).status_code == 401
    assert client.post("/session", json={"host": True, "password": "nope"}).status_code == 401
    assert terminal._tickets == {}


def test_session_for_the_host_issues_a_ticket_that_works_once(client):
    response = client.post("/session", json={"host": True, "password": PASSWORD, "cols": 100, "rows": 30})
    ticket = response.get_json()["ticket"]

    entry = terminal._consume_ticket(ticket)

    assert response.status_code == 200
    assert entry["host"] and entry["kind"] == "pty" and entry["cols"] == 100
    assert terminal._consume_ticket(ticket) is None


def test_third_host_session_is_refused_and_the_container_pool_is_separate(client):
    for _ in range(host.HOST_MAX_SESSIONS):
        terminal._sessions.add(FakeSession({"host": True}))

    response = client.post("/session", json={"host": True, "password": PASSWORD})

    assert response.status_code == 429
    assert response.get_json()["code"] == "host_limit"
    assert terminal._active_session_count() == 0

    terminal._sessions.clear()
    for _ in range(terminal.MAX_SESSIONS):
        terminal._sessions.add(FakeSession({}))

    assert terminal._active_host_count() == 0
    assert client.post("/session", json={"host": True, "password": PASSWORD}).status_code == 200


# ---- idle ----


def test_idle_watch_ends_a_quiet_session(monkeypatch):
    monkeypatch.setattr(host, "HOST_IDLE_TIMEOUT", 0.05)
    session = SimpleNamespace(last_input=time.monotonic())

    assert asyncio.run(asyncio.wait_for(terminal._watch_idle(session), 5)) == "idle"


def test_typing_keeps_a_session_alive(monkeypatch):
    monkeypatch.setattr(host, "HOST_IDLE_TIMEOUT", 600)
    session = SimpleNamespace(last_input=time.monotonic())

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(asyncio.wait_for(terminal._watch_idle(session), 0.2))


# ---- the real thing: a native pty session ----


def test_native_pty_session_runs_a_real_shell_and_ends_cleanly():
    entry = {"host": True, "kind": "pty", "cols": 80, "rows": 24, "windows": False}
    session = terminal._make_session(entry)

    session.open()

    try:
        assert isinstance(session, terminal.HostPtySession)
        assert terminal._active_host_count() == 1

        session.raw.sendall(b"echo hd-$((20+22))\nexit 3\n")
        output = b""
        deadline = time.time() + 10

        while time.time() < deadline and b"hd-42" not in output:
            chunk = session.recv()

            if not chunk:
                break

            output += chunk

        assert b"hd-42" in output
        assert session.exit_code() == 3
    finally:
        session.close()

    assert terminal._active_host_count() == 0
    assert session.process.poll() is not None


def test_pty_close_kills_a_shell_that_is_still_running():
    session = terminal._make_session({"host": True, "kind": "pty", "cols": 80, "rows": 24, "windows": False})
    session.open()
    session.close()

    assert session.process.wait(timeout=5) is not None

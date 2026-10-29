import datetime
import os
import ssl

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from pymodules import hd_CertManager as manager
from pymodules import hd_CertScheduler as scheduler
from pymodules import hd_DomainStore as store
from pymodules import hd_FunctionsNativeSSL as native
from pymodules.hd_ACMEClient import ACMEError


class FakeTimer:
    created = []

    def __init__(self, delay, callback):
        self.delay, self.callback, self.started, self.daemon = delay, callback, False, False
        FakeTimer.created.append(self)

    def start(self):
        self.started = True


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    FakeTimer.created.clear()
    scheduler._state.update(timer=None, failures=0, last_error=None, next_attempt=None, reissue_at=None)
    monkeypatch.setattr(scheduler.threading, "Timer", FakeTimer)


def test_three_edits_inside_the_window_make_one_scheduled_order():
    assert scheduler.schedule_reissue() is True
    assert scheduler.schedule_reissue() is False
    assert scheduler.schedule_reissue() is False

    assert len(FakeTimer.created) == 1
    assert FakeTimer.created[0].delay == 60 and FakeTimer.created[0].started


def test_three_domain_edits_fire_one_reissue(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "domains_file", str(tmp_path / "domains.json"))
    monkeypatch.setattr(store, "_listeners", [scheduler.schedule_reissue])
    monkeypatch.setattr(store, "reserved_hosts", lambda: set())
    store.reset_cache()

    store.add_domain("one", "a.example.com", 80)
    store.add_domain("one", "b.example.com", 80)
    store.remove_domain("one", "a.example.com")

    assert len(FakeTimer.created) == 1

    runs = []
    monkeypatch.setattr(scheduler, "run_reissue", lambda: runs.append(1))
    FakeTimer.created[0].callback()

    assert runs == [1]
    assert scheduler.schedule_reissue() is True


def test_backoff_doubles_from_an_hour_and_caps_at_a_day():
    assert [scheduler.backoff_delay(n) for n in range(0, 7)] == [0, 3600, 7200, 14400, 28800, 57600, 86400]
    assert scheduler.backoff_delay(40) == 86400


def test_failures_set_the_retry_delay_and_success_resets_it():
    assert scheduler.retry_delay(43200) == 43200

    assert scheduler.record_failure("boom") == 3600
    assert scheduler.record_failure("boom") == 7200
    assert scheduler.retry_delay(43200) == 7200
    assert scheduler.get_schedule_state()["last_error"] == "boom"

    scheduler.record_success()
    assert scheduler.retry_delay(43200) == 43200
    assert scheduler.get_schedule_state()["next_attempt"] is None


def managed(monkeypatch, certificate_names):
    monkeypatch.setattr(scheduler, "renewal_status", lambda: {"managed": True, "domain": "home.example.com"})
    monkeypatch.setattr(scheduler, "get_state", lambda: {"running": False})
    monkeypatch.setattr(scheduler, "get_cert_domains_and_type", lambda: {"domains": certificate_names})


def plan_of(*names):
    return {"covered": list(names), "excluded": [], "challenges": {}}


def test_reissue_skips_when_nothing_changed(monkeypatch):
    managed(monkeypatch, ["home.example.com", "*.home.example.com"])
    monkeypatch.setattr(scheduler, "plan_names", lambda d: plan_of("home.example.com", "*.home.example.com"))
    monkeypatch.setattr(scheduler, "issue_certificate", lambda *a, **k: pytest.fail("ordered again"))

    assert scheduler.run_reissue(log=lambda *_: None) == "unchanged"


def test_reissue_orders_when_names_changed(monkeypatch):
    managed(monkeypatch, ["home.example.com", "*.home.example.com"])
    monkeypatch.setattr(scheduler, "plan_names", lambda d: plan_of("home.example.com", "*.home.example.com", "app.other.org"))
    monkeypatch.setattr(scheduler, "issue_certificate", lambda domain, **k: {"domains": k["plan"]["covered"]})

    assert scheduler.run_reissue(log=lambda *_: None) == "issued"
    assert scheduler.get_schedule_state()["failures"] == 0


def test_failed_reissue_backs_off_and_schedules_a_retry(monkeypatch):
    managed(monkeypatch, ["home.example.com"])
    monkeypatch.setattr(scheduler, "plan_names", lambda d: plan_of("home.example.com", "app.other.org"))

    def fail(*a, **k):
        raise ACMEError("validation failed")

    monkeypatch.setattr(scheduler, "issue_certificate", fail)

    assert scheduler.run_reissue(log=lambda *_: None) == "failed"
    assert FakeTimer.created[-1].delay == 3600
    assert scheduler.get_schedule_state()["last_error"] == "validation failed"


def test_reissue_waits_while_another_order_runs(monkeypatch):
    managed(monkeypatch, [])
    monkeypatch.setattr(scheduler, "get_state", lambda: {"running": True})

    assert scheduler.run_reissue(log=lambda *_: None) == "busy"
    assert FakeTimer.created[-1].delay == 60


def test_unmanaged_install_never_reissues(monkeypatch):
    monkeypatch.setattr(scheduler, "renewal_status", lambda: {"managed": False})

    assert scheduler.run_reissue(log=lambda *_: None) == "skipped"


def test_per_name_status_and_last_error(monkeypatch, tmp_path):
    monkeypatch.setattr(manager, "STATUS_FILE", str(tmp_path / "status.json"))
    monkeypatch.setattr(manager, "read_config", lambda: {"base_domain": "home.example.com"})
    monkeypatch.setattr(manager, "ssl_enabled", lambda: True)
    monkeypatch.setattr(manager, "get_cert_domains_and_type", lambda: {"domains": ["home.example.com", "*.home.example.com", "ok.other.org"]})
    manager._save_last_run(excluded=[{"name": "bad.other.org", "reason": "its DNS name does not resolve"}], error="order failed")

    names = ["ok.other.org", "bad.other.org", "new.other.org", "app.homedock.local", "app.home.example.com"]
    result = {item["name"]: item for item in manager.name_statuses(names)}

    assert result["ok.other.org"]["status"] == "covered"
    assert result["app.home.example.com"]["status"] == "covered"
    assert result["bad.other.org"] == {"name": "bad.other.org", "status": "excluded", "reason": "its DNS name does not resolve"}
    assert result["new.other.org"]["status"] == "pending"
    assert result["app.homedock.local"]["status"] == "excluded"
    assert result["home.example.com"]["status"] == "covered"
    assert manager.load_last_run()["error"] == "order failed"


def make_cert(directory, name):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False).sign(key, hashes.SHA256())
    )
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "fullchain.pem"), "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(os.path.join(directory, "privkey.pem"), "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))


def test_reload_swaps_the_certificate_for_new_connections(tmp_path):
    import socket
    import threading

    old, new = str(tmp_path / "old"), str(tmp_path / "new")
    make_cert(old, "old.example.test")
    make_cert(new, "new.example.test")

    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(os.path.join(old, "fullchain.pem"), os.path.join(old, "privkey.pem"))
    native._live_context["context"] = server_context

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]

    def serve():
        while True:
            try:
                connection, _ = listener.accept()
                with server_context.wrap_socket(connection, server_side=True):
                    pass
            except (OSError, ssl.SSLError):
                if listener.fileno() == -1:
                    return

    threading.Thread(target=serve, daemon=True).start()

    def served_name():
        client = ssl.create_default_context()
        client.check_hostname = False
        client.verify_mode = ssl.CERT_NONE

        with socket.create_connection(("127.0.0.1", port)) as raw, client.wrap_socket(raw) as tls:
            return x509.load_der_x509_certificate(tls.getpeercert(binary_form=True)).subject.rfc4514_string()

    try:
        assert served_name() == "CN=old.example.test"
        assert native.reload_ssl_context(new) is True
        assert served_name() == "CN=new.example.test"
    finally:
        native._live_context["context"] = None
        listener.close()

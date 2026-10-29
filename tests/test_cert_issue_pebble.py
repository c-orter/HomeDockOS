import os

import pytest
from cryptography import x509

from pymodules import hd_CertManager as manager
from pymodules import hd_CertPlan as plan

pytestmark = pytest.mark.pebble

BASE = "home.example.test"
ME = {"203.0.113.5"}


def entry(zone, token="t"):
    return {"zone": zone, "provider": "cloudflare", "token": token}


@pytest.fixture
def issue(pebble_dns, tmp_path, monkeypatch):
    records = pebble_dns["records"]
    records.clear()
    published = []
    probed = []

    def set_txt(identifier, token, value):
        published.append((identifier, token))
        records.setdefault(f"_acme-challenge.{identifier}", []).append(value)

    def clear_txt(identifier, token):
        records.pop(f"_acme-challenge.{identifier}", None)

    monkeypatch.setattr(manager, "get_provider", lambda name: {"set": set_txt, "clear": clear_txt})
    monkeypatch.setattr(manager, "wait_for_txt", lambda identifier, txt, **kw: probed.append(identifier) or True)
    monkeypatch.setattr(manager, "get_ssl_cert_directory", lambda: str(tmp_path / "live"))
    monkeypatch.setattr(manager, "migrate_legacy_acme", lambda log=print: False)
    manager._set_state(running=False)

    def run(entries, names, resolver):
        monkeypatch.setattr(manager, "load_credentials", lambda: entries)
        cert_dir = str(tmp_path / "out")
        result = manager.issue_certificate(
            BASE,
            plan=plan.plan_names(BASE, names=names, entries=entries, resolver=resolver, addresses=ME),
            cert_dir=cert_dir,
            directory_url=pebble_dns["directory"],
            verify=pebble_dns["ca"],
            account_key=str(tmp_path / "account.key"),
            log=lambda *_: None,
        )
        with open(os.path.join(cert_dir, "cert.pem"), "rb") as handle:
            san = x509.load_pem_x509_certificate(handle.read()).extensions.get_extension_for_class(x509.SubjectAlternativeName)

        return result, sorted(san.value.get_values_for_type(x509.DNSName)), published, probed

    return run


def test_one_cert_for_base_wildcard_and_off_domain_name(issue):
    entries = [entry(BASE, "base-token"), entry("other.test", "other-token")]

    result, san, published, probed = issue(entries, ["app.other.test"], lambda name: ["203.0.113.5"])

    assert san == sorted([BASE, f"*.{BASE}", "app.other.test"])
    assert result["excluded"] == []
    assert ("app.other.test", "other-token") in published
    assert (BASE, "base-token") in published
    assert "app.other.test" in probed


def test_uncovered_name_is_reported_while_the_rest_issue(issue):
    result, san, _, _ = issue([entry(BASE)], ["app.nowhere.test"], lambda name: ["203.0.113.5"])

    assert san == sorted([BASE, f"*.{BASE}"])
    assert result["excluded"] == [{"name": "app.nowhere.test", "reason": "no DNS provider covers its zone"}]

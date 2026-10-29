import json

import pytest

from pymodules import hd_AcmeCredentials as creds
from pymodules import hd_CertPlan as plan
from pymodules import hd_CertManager as manager
from pymodules.hd_ACMEClient import ACMEError

ME = {"203.0.113.5"}


def entry(zone, provider="cloudflare", token="t"):
    return {"zone": zone, "provider": provider, "token": token}


def resolver_for(table):
    return lambda name: table.get(name, [])


def test_longest_zone_suffix_wins():
    entries = [entry("example.com", token="a"), entry("home.example.com", token="b")]

    assert creds.match_credential("app.home.example.com", entries)["token"] == "b"
    assert creds.match_credential("other.example.com", entries)["token"] == "a"
    assert creds.match_credential("*.home.example.com", entries)["token"] == "b"
    assert creds.match_credential("example.org", entries) is None
    assert creds.match_credential("notexample.com", entries) is None


def test_single_record_providers_only_cover_their_own_name():
    entries = [entry("me.duckdns.org", "duckdns")]

    assert creds.match_credential("me.duckdns.org", entries)
    assert creds.match_credential("*.me.duckdns.org", entries)
    assert creds.match_credential("app.me.duckdns.org", entries) is None


def test_plan_covers_base_wildcard_and_covered_off_domain_name():
    entries = [entry("home.example.com"), entry("other.org")]

    result = plan.plan_names("home.example.com", names=["app.other.org"], entries=entries, resolver=resolver_for({"app.other.org": ["203.0.113.5"]}), addresses=ME)

    assert result["covered"] == ["home.example.com", "*.home.example.com", "app.other.org"]
    assert result["excluded"] == []
    assert set(result["challenges"].values()) == {"dns-01"}


def test_name_without_provider_is_excluded_and_others_still_go():
    entries = [entry("home.example.com")]

    result = plan.plan_names("home.example.com", names=["app.nowhere.net", "x.home.example.com"], entries=entries, resolver=resolver_for({}), addresses=ME)

    assert result["covered"] == ["home.example.com", "*.home.example.com"]
    assert result["excluded"] == [{"name": "app.nowhere.net", "reason": "its DNS name does not resolve"}]


def test_name_without_provider_falls_back_to_http_01_but_wildcards_never_do():
    result = plan.plan_names("home.example.com", names=["app.nowhere.net"], entries=[entry("home.example.com")], resolver=resolver_for({"app.nowhere.net": ["203.0.113.5"]}), addresses=ME)

    assert result["challenges"]["app.nowhere.net"] == "http-01"
    assert result["challenges"]["*.home.example.com"] == "dns-01"
    assert not any(name.startswith("*.") and kind == "http-01" for name, kind in result["challenges"].items())


def test_name_not_pointing_here_is_excluded_with_reason():
    entries = [entry("home.example.com"), entry("other.org")]

    result = plan.plan_names("home.example.com", names=["a.other.org", "b.other.org"], entries=entries, resolver=resolver_for({"a.other.org": ["198.51.100.9"]}), addresses=ME)

    assert [item["name"] for item in result["excluded"]] == ["a.other.org", "b.other.org"]
    assert "198.51.100.9" in result["excluded"][0]["reason"]
    assert "does not resolve" in result["excluded"][1]["reason"]


def test_one_label_under_base_rides_the_wildcard_but_deeper_names_do_not():
    entries = [entry("home.example.com")]
    table = {"a.b.home.example.com": ["203.0.113.5"]}

    result = plan.plan_names("home.example.com", names=["app.home.example.com", "a.b.home.example.com"], entries=entries, resolver=resolver_for(table), addresses=ME)

    assert "app.home.example.com" not in result["covered"]
    assert "a.b.home.example.com" in result["covered"]


def test_local_names_never_go_on_the_certificate():
    result = plan.plan_names("home.example.com", names=["app.homedock.local"], entries=[entry("home.example.com")], resolver=resolver_for({}), addresses=ME)

    assert result["excluded"][0]["name"] == "app.homedock.local"


def test_no_credential_for_base_covers_nothing():
    result = plan.plan_names("home.example.com", names=[], entries=[], resolver=resolver_for({}), addresses=ME)

    assert result["covered"] == []
    assert [item["name"] for item in result["excluded"]] == ["home.example.com", "*.home.example.com"]


def test_name_limit(monkeypatch):
    monkeypatch.setattr(plan, "MAX_NAMES", 3)
    table = {f"n{i}.other.org": ["203.0.113.5"] for i in range(3)}

    result = plan.plan_names("home.example.com", names=list(table), entries=[entry("home.example.com"), entry("other.org")], resolver=resolver_for(table), addresses=ME)

    assert len(result["covered"]) == 3
    assert all("at most" in item["reason"] for item in result["excluded"])


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(creds, "CREDENTIALS_FILE", str(tmp_path / "credentials.json"))
    return tmp_path


def test_legacy_global_pair_migrates_to_base_domain_entry(store, monkeypatch):
    monkeypatch.setattr(creds, "read_config", lambda: {"base_domain": "Home.Example.com.", "acme_provider": "cloudflare", "acme_token": "secret"})

    assert creds.load_credentials() == [entry("home.example.com", token="secret")]
    assert json.load(open(creds.CREDENTIALS_FILE)) == [entry("home.example.com", token="secret")]

    monkeypatch.setattr(creds, "read_config", lambda: {"base_domain": "", "acme_provider": "", "acme_token": ""})
    assert creds.load_credentials()[0]["zone"] == "home.example.com"


def test_removing_the_last_entry_does_not_remigrate(store, monkeypatch):
    monkeypatch.setattr(creds, "read_config", lambda: {"base_domain": "a.example.com", "acme_provider": "cloudflare", "acme_token": "x"})
    creds.load_credentials()

    assert creds.remove_credential("a.example.com")
    assert creds.load_credentials() == []


def test_set_and_replace_credential(store, monkeypatch):
    monkeypatch.setattr(creds, "read_config", lambda: {})

    creds.set_credential("example.com", "cloudflare", "one")
    creds.set_credential("example.com", "cloudflare", "two")

    assert creds.load_credentials() == [entry("example.com", token="two")]
    assert creds.public_credentials() == [{"zone": "example.com", "provider": "cloudflare"}]
    assert creds.stored_token("example.com", "duckdns") == ""

    with pytest.raises(creds.CredentialError):
        creds.set_credential("example.com", "nope", "t")


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.answered = []

    def register(self): pass

    def new_order(self, domains):
        self.domains = domains
        return {"authorizations": domains}

    def challenges(self, order, methods):
        return [{"authorization_url": f"auth/{d}", "challenge_url": f"chal/{d}", "type": "dns-01", "value": f"txt-{d}", "identifier": d.lstrip("*."), "name": d, "token": "t"} for d in order["authorizations"]]

    def answer_challenge(self, url): self.answered.append(url)
    def wait_for_authorization(self, url): return True
    def finalize(self, order, csr): return "cert-url"
    def download_certificate(self, url): return "pem"


def test_each_authorization_reaches_its_own_provider_and_probe(monkeypatch, tmp_path):
    calls = []
    probes = []

    def provider(name):
        return {
            "set": lambda identifier, token, value: calls.append((name, "set", identifier, token)),
            "clear": lambda identifier, token: calls.append((name, "clear", identifier, token)),
        }

    entries = [entry("home.example.com", "duckdns", "t-home"), entry("other.org", "cloudflare", "t-cf")]
    result = {"covered": ["home.example.com", "other.org"], "excluded": [{"name": "x.net", "reason": "its DNS name does not resolve"}], "challenges": {}}

    monkeypatch.setattr(manager, "load_credentials", lambda: entries)
    monkeypatch.setattr(manager, "get_provider", provider)
    monkeypatch.setattr(manager, "ACMEClient", FakeClient)
    monkeypatch.setattr(manager.ACMEClient, "build_csr", staticmethod(lambda domains, key: None), raising=False)
    monkeypatch.setattr(manager, "generate_certificate_key", lambda: None)
    monkeypatch.setattr(manager, "wait_for_txt", lambda identifier, txt, **kw: probes.append(identifier) or True)
    monkeypatch.setattr(manager, "_write_bundle", lambda *a: ["fullchain.pem"])
    monkeypatch.setattr(manager, "migrate_legacy_acme", lambda log=print: False)
    monkeypatch.setattr(manager, "get_ssl_cert_directory", lambda: str(tmp_path))
    monkeypatch.setattr(manager, "reload_ssl_context", lambda d: True)

    out = manager.issue_certificate("home.example.com", plan=result, log=lambda *_: None)

    assert out["domains"] == ["home.example.com", "other.org"]
    assert out["excluded"] == result["excluded"]
    assert probes == ["home.example.com", "other.org"]
    # Cloudflare publishes up front (batched), DuckDNS one authorization at a time
    assert [c for c in calls if c[1] == "set"] == [("cloudflare", "set", "other.org", "t-cf"), ("duckdns", "set", "home.example.com", "t-home")]
    assert {c[2] for c in calls if c[1] == "clear"} == {"home.example.com", "other.org"}
    assert manager.get_state()["plan"]["excluded"] == result["excluded"]


def test_issue_refuses_when_base_is_not_covered(monkeypatch):
    monkeypatch.setattr(manager, "load_credentials", lambda: [])

    with pytest.raises(ACMEError, match="base domain"):
        manager.issue_certificate("home.example.com", plan={"covered": [], "excluded": [{"name": "home.example.com", "reason": "no DNS provider covers the base domain"}], "challenges": {}})

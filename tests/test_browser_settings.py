import asyncio
import json
from collections import defaultdict
from types import SimpleNamespace

import bcrypt
import pytest
from flask import Flask
from flask_login import LoginManager

from pymodules import hd_BrowserAllowlist as allowlist
from pymodules import hd_BrowserEgressProxy as proxy
from pymodules import hd_BrowserRuntime as runtime
from pymodules import hd_BrowserSettings as settings
from pymodules import hd_HostShell as host_shell
from pymodules import hd_UIBrowser as browser


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_FOLDER", str(tmp_path / "_browser"))
    monkeypatch.setattr(settings, "SETTINGS_FILE", str(tmp_path / "_browser" / "settings.json"))
    monkeypatch.setattr(allowlist, "BROWSER_FOLDER", str(tmp_path / "_browser"))
    monkeypatch.setattr(allowlist, "ALLOWLIST_FILE", str(tmp_path / "_browser" / "allowlist.json"))
    monkeypatch.setattr(allowlist, "AUDIT_FILE", str(tmp_path / "logs" / "browser.log"))
    monkeypatch.setattr(host_shell, "_failures", defaultdict(list))
    browser.revoke_tickets()


# settings


def test_defaults_are_two_gb_one_cpu_and_a_pids_cap():
    assert settings.load() == {"idle_minutes": 15, "memory_mb": 2048, "cpus": 1.0, "pids": 512}
    assert settings.limits() == {"mem_limit": "2048m", "shm_size": "1024m", "pids_limit": 512, "nano_cpus": 1_000_000_000}


def test_valid_values_are_saved_and_survive_a_reload():
    saved = settings.save({"idle_minutes": 30, "memory_mb": 4096, "cpus": 2, "pids": 1024})

    assert saved == {"idle_minutes": 30, "memory_mb": 4096, "cpus": 2.0, "pids": 1024}
    assert settings.load() == saved
    assert settings.limits()["shm_size"] == "2048m"


def test_a_partial_save_keeps_the_other_fields():
    settings.save({"memory_mb": 1024})

    assert settings.save({"idle_minutes": 5}) == {"idle_minutes": 5, "memory_mb": 1024, "cpus": 1.0, "pids": 512}


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"idle_minutes": 0}, "idle_minutes"),
        ({"idle_minutes": 1441}, "idle_minutes"),
        ({"idle_minutes": 1.5}, "idle_minutes"),
        ({"memory_mb": 100}, "memory_mb"),
        ({"memory_mb": 99999}, "memory_mb"),
        ({"cpus": 0}, "cpus"),
        ({"cpus": 64}, "cpus"),
        ({"pids": 10}, "pids"),
        ({"pids": "lots"}, "pids"),
        ({"pids": None}, "pids"),
        ({"pids": True}, "pids"),
        ({"cpus": float("nan")}, "cpus"),
        ({"memory_mb": [1]}, "memory_mb"),
    ],
)
def test_invalid_values_are_rejected_naming_the_field_and_nothing_is_saved(payload, field):
    with pytest.raises(settings.SettingsError) as refused:
        settings.save(payload)

    assert refused.value.field == field and refused.value.message
    assert settings.load() == settings.DEFAULTS


def test_cpus_snap_to_half_steps():
    assert settings.save({"cpus": "1.2"})["cpus"] == 1.0
    assert settings.save({"cpus": 1.8})["cpus"] == 2.0


def test_a_damaged_settings_file_falls_back_to_the_defaults(tmp_path):
    (tmp_path / "_browser").mkdir()
    (tmp_path / "_browser" / "settings.json").write_text("{not json")

    assert settings.load() == settings.DEFAULTS

    (tmp_path / "_browser" / "settings.json").write_text(json.dumps({"memory_mb": 99999999, "pids": 700}))

    assert settings.load()["memory_mb"] == 2048 and settings.load()["pids"] == 700


def test_the_hardening_uses_the_saved_limits_and_nothing_else_changes():
    settings.save({"memory_mb": 3000, "cpus": 3, "pids": 800})
    spec = runtime._hardening()

    assert (spec["mem_limit"], spec["memswap_limit"], spec["shm_size"], spec["pids_limit"], spec["nano_cpus"]) == ("3000m", "3000m", "1500m", 800, 3_000_000_000)
    assert spec["cap_drop"] == ["ALL"] and spec["privileged"] is False and "no-new-privileges" in spec["security_opt"]


# allowlist entries


def test_the_allowlist_starts_empty():
    assert allowlist.entries() == []
    assert allowlist.proxy_rules() == {"allow": [], "deny": []}


@pytest.mark.parametrize(
    "raw,expected",
    [
        ({"kind": "ip", "value": "192.168.1.20"}, ("ip", "192.168.1.20", None)),
        ({"kind": "ip", "value": "192.168.1.20", "port": "8080"}, ("ip", "192.168.1.20", 8080)),
        ({"kind": "subnet", "value": "192.168.1.5/24"}, ("subnet", "192.168.1.0/24", None)),
        ({"kind": "host", "value": "NAS.Home.Lan", "port": 443}, ("host", "nas.home.lan", 443)),
        ({"kind": "app", "value": "jellyfin"}, ("app", "jellyfin", None)),
        ({"kind": "ip", "value": "fd00::5"}, ("ip", "fd00::5", None)),
    ],
)
def test_good_entries_are_normalised(raw, expected):
    clean = allowlist.parse_entry(raw)

    assert (clean["kind"], clean["value"], clean["port"]) == expected


@pytest.mark.parametrize(
    "raw",
    [
        {"kind": "ip", "value": "127.0.0.1"},
        {"kind": "ip", "value": "::1"},
        {"kind": "ip", "value": "169.254.169.254"},
        {"kind": "ip", "value": "224.0.0.1"},
        {"kind": "ip", "value": "0.0.0.0"},
        {"kind": "ip", "value": "not-an-ip"},
        {"kind": "subnet", "value": "0.0.0.0/0"},
        {"kind": "subnet", "value": "10.0.0.0/4"},
        {"kind": "subnet", "value": "127.0.0.0/8"},
        {"kind": "subnet", "value": "169.254.0.0/16"},
        {"kind": "subnet", "value": "192.168.0.0/33"},
        {"kind": "host", "value": "*.lan"},
        {"kind": "host", "value": "localhost"},
        {"kind": "host", "value": "bad host"},
        {"kind": "host", "value": ""},
        {"kind": "app", "value": "../etc"},
        {"kind": "app", "value": "a b"},
        {"kind": "magic", "value": "x"},
        {"kind": "ip", "value": "10.0.0.1", "port": 2375},
        {"kind": "ip", "value": "10.0.0.1", "port": 2376},
        {"kind": "ip", "value": "10.0.0.1", "port": 70000},
        {"kind": "ip", "value": "10.0.0.1", "port": "x"},
        "not an object",
        None,
    ],
)
def test_entries_that_could_never_be_safe_are_refused(raw):
    with pytest.raises(allowlist.AllowlistError):
        allowlist.parse_entry(raw)


def test_adding_stores_the_entry_and_a_duplicate_is_not_added_twice():
    first = allowlist.add({"kind": "ip", "value": "192.168.1.20"})
    again = allowlist.add({"kind": "ip", "value": "192.168.1.20"})

    assert first["id"] == again["id"]
    assert len(allowlist.entries()) == 1


def test_the_allowlist_has_a_size_limit(monkeypatch):
    monkeypatch.setattr(allowlist, "MAX_ENTRIES", 2)
    allowlist.add({"kind": "ip", "value": "10.0.0.1"})
    allowlist.add({"kind": "ip", "value": "10.0.0.2"})

    with pytest.raises(allowlist.AllowlistError):
        allowlist.add({"kind": "ip", "value": "10.0.0.3"})


def test_entries_become_proxy_rules_with_the_deny_list():
    allowlist.add({"kind": "subnet", "value": "192.168.1.0/24", "port": 80})
    allowlist.add({"kind": "host", "value": "nas.lan"})
    allowlist.add({"kind": "app", "value": "jellyfin", "port": 8096})

    rules = allowlist.proxy_rules(["10.1.1.1", "10.1.1.1", "172.17.0.1"])

    assert rules["allow"] == [{"port": 80, "net": "192.168.1.0/24"}, {"port": None, "host": "nas.lan"}, {"port": 8096, "host": "jellyfin"}]
    assert rules["deny"] == ["10.1.1.1", "172.17.0.1"]
    assert allowlist.has_apps() is True


def test_a_tampered_file_cannot_smuggle_in_an_unsafe_entry(tmp_path):
    (tmp_path / "_browser").mkdir()
    (tmp_path / "_browser" / "allowlist.json").write_text(json.dumps({"entries": [{"id": "a", "kind": "ip", "value": "127.0.0.1"}, {"id": "b", "kind": "ip", "value": "10.0.0.9"}]}))

    assert [e["value"] for e in allowlist.entries()] == ["10.0.0.9"]


# the proxy enforcing the list


def run(coro):
    return asyncio.run(coro)


class Loop:
    def __init__(self, answers):
        self.answers = answers

    async def getaddrinfo(self, host, port, type=0):
        return [(0, 0, 0, "", (a, port)) for a in self.answers]


def resolve(host, port, answers, **rules):
    return run(proxy.resolve(host, port, Loop(answers), proxy.Rules(**rules)))


def test_nothing_private_is_reachable_with_an_empty_list():
    with pytest.raises(proxy.Refused):
        resolve("192.168.1.20", 80, [])

    with pytest.raises(proxy.Refused):
        resolve("nas.lan", 80, ["192.168.1.20"])


def test_an_ip_entry_opens_exactly_that_address_and_port():
    rules = {"allow": [{"net": "192.168.1.20/32", "port": 8080}]}

    assert resolve("192.168.1.20", 8080, [], **rules) == "192.168.1.20"

    for host, port in (("192.168.1.20", 80), ("192.168.1.21", 8080)):
        with pytest.raises(proxy.Refused):
            resolve(host, port, [], **rules)


def test_a_subnet_entry_opens_its_range_only():
    rules = {"allow": [{"net": "192.168.1.0/24"}]}

    assert resolve("192.168.1.99", 443, [], **rules) == "192.168.1.99"

    with pytest.raises(proxy.Refused):
        resolve("192.168.2.1", 443, [], **rules)


def test_a_host_entry_opens_only_that_name():
    rules = {"allow": [{"host": "nas.lan"}]}

    assert resolve("nas.lan", 80, ["192.168.1.20"], **rules) == "192.168.1.20"
    assert resolve("NAS.LAN", 80, ["192.168.1.20"], **rules) == "192.168.1.20"

    with pytest.raises(proxy.Refused):
        resolve("other.lan", 80, ["192.168.1.20"], **rules)


def test_dns_rebinding_cannot_borrow_an_allowed_range():
    """A name nobody allowed that now resolves into an allowed subnet is still a name nobody allowed... the subnet entry is about the address, so the check is on the address the name resolves to, and the connection goes to that address."""

    rules = {"allow": [{"net": "192.168.1.0/24"}]}

    assert resolve("rebind.example", 80, ["192.168.1.5"], **rules) == "192.168.1.5"

    with pytest.raises(proxy.Refused):
        resolve("rebind.example", 80, ["192.168.1.5", "10.0.0.1"], **rules)


def test_a_name_that_answers_with_a_public_and_a_loopback_address_is_refused():
    with pytest.raises(proxy.Refused):
        resolve("mixed.example", 80, ["1.1.1.1", "127.0.0.1"], allow=[{"host": "mixed.example"}])


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "0.0.0.0", "224.0.0.1", "::1", "fe80::1", "::ffff:127.0.0.1", "::ffff:169.254.169.254"])
def test_no_entry_can_open_loopback_metadata_or_multicast(address):
    rules = {"allow": [{"net": "0.0.0.0/0"}, {"net": "::/0"}, {"host": "evil.example"}]}

    with pytest.raises(proxy.Refused):
        resolve("evil.example", 80, [address], **rules)


@pytest.mark.parametrize("port", [2375, 2376])
def test_no_entry_can_open_the_container_engine_api(port):
    with pytest.raises(proxy.Refused):
        resolve("192.168.1.20", port, [], allow=[{"net": "192.168.1.0/24"}])


def test_the_deny_list_wins_over_the_allow_list():
    rules = {"allow": [{"net": "192.168.1.0/24"}], "deny": ["192.168.1.1", "10.9.0.0/16"]}

    with pytest.raises(proxy.Refused):
        resolve("192.168.1.1", 80, [], **rules)

    assert resolve("192.168.1.2", 80, [], **rules) == "192.168.1.2"


def test_homedocks_own_public_address_stays_denied():
    with pytest.raises(proxy.Refused):
        resolve("my.server.example", 443, ["93.184.216.34"], deny=["93.184.216.34"])

    assert resolve("my.server.example", 443, ["93.184.216.35"], deny=["93.184.216.34"]) == "93.184.216.35"


def test_a_mapped_address_cannot_dodge_the_deny_list():
    with pytest.raises(proxy.Refused):
        resolve("x.example", 80, ["::ffff:192.168.1.1"], allow=[{"net": "192.168.1.0/24"}], deny=["192.168.1.1"])


def test_rules_arrive_through_the_environment_and_bad_ones_open_nothing():
    rules = proxy.Rules.from_env({"HD_EGRESS_RULES": json.dumps({"allow": [{"net": "10.0.0.0/24"}], "deny": ["10.0.0.5"]})})

    assert rules.permits("x", "10.0.0.9", 80) and rules.denied("10.0.0.5")

    for broken in ("{", "[]", '{"allow": [{"net": "garbage"}]}', ""):
        assert not proxy.Rules.from_env({"HD_EGRESS_RULES": broken}).permits("x", "10.0.0.9", 80)


def test_the_proxy_container_is_started_with_the_rules(monkeypatch):
    allowlist.add({"kind": "ip", "value": "192.168.1.20"})
    created = []
    connected = []
    proxy_container = SimpleNamespace(status="running", reload=lambda: None, start=lambda: None, remove=lambda force=False: None)
    client = SimpleNamespace(
        containers=SimpleNamespace(create=lambda image, **kw: created.append(kw) or proxy_container, get=lambda name: (_ for _ in ()).throw(runtime.docker.errors.NotFound("x"))),
        networks=SimpleNamespace(list=lambda names=None: [], create=lambda name, **kw: SimpleNamespace(name=name, attrs={"Internal": kw.get("internal", False)}), get=lambda name: SimpleNamespace(connect=lambda c: connected.append(name))),
        images=SimpleNamespace(get=lambda ref: object()),
    )
    monkeypatch.setattr(runtime, "is_docker", False)
    monkeypatch.setattr(runtime, "_deny_addresses", lambda c: {"172.17.0.1"})

    runtime._start_proxy(client, SimpleNamespace(connect=lambda c, aliases=None: None))

    rules = json.loads(created[0]["environment"]["HD_EGRESS_RULES"])

    assert rules == {"allow": [{"port": None, "net": "192.168.1.20"}], "deny": ["172.17.0.1"]}
    assert connected == []


def test_the_proxy_only_joins_the_app_network_when_an_app_is_allowed(monkeypatch):
    allowlist.add({"kind": "app", "value": "jellyfin"})
    connected = []
    proxy_container = SimpleNamespace(status="running", reload=lambda: None, start=lambda: None, remove=lambda force=False: None)
    client = SimpleNamespace(
        containers=SimpleNamespace(create=lambda image, **kw: proxy_container, get=lambda name: (_ for _ in ()).throw(runtime.docker.errors.NotFound("x"))),
        networks=SimpleNamespace(list=lambda names=None: [], create=lambda name, **kw: SimpleNamespace(name=name, attrs={}), get=lambda name: SimpleNamespace(connect=lambda c: connected.append(name))),
        images=SimpleNamespace(get=lambda ref: object()),
    )
    monkeypatch.setattr(runtime, "_deny_addresses", lambda c: set())

    runtime._start_proxy(client, SimpleNamespace(connect=lambda c, aliases=None: None))

    assert connected == [runtime.APP_NETWORK_NAME]


def test_homedocks_own_addresses_and_the_hosts_gateways_are_denied(monkeypatch):
    own = SimpleNamespace(reload=lambda: None, attrs={"NetworkSettings": {"Networks": {"bridge": {"IPAddress": "172.17.0.2", "GlobalIPv6Address": ""}, "homedock_network": {"IPAddress": "172.20.0.2"}}}})
    gateway = lambda ip: [SimpleNamespace(attrs={"IPAM": {"Config": [{"Gateway": ip}]}})]
    client = SimpleNamespace(networks=SimpleNamespace(list=lambda names=None: gateway("172.17.0.1")))
    monkeypatch.setattr(runtime, "is_docker", True)
    monkeypatch.setattr(runtime, "own_container", lambda c: own)
    monkeypatch.setattr(runtime.socket, "gethostbyname", lambda name: "192.168.1.2")

    denied = runtime._deny_addresses(client)

    assert {"172.17.0.2", "172.20.0.2", "172.17.0.1", "192.168.1.2"} <= denied


# the API


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    LoginManager(app).user_loader(lambda user_id: None)

    for rule, view in (
        ("/settings", browser.api_browser_settings),
        ("/settings/save", browser.api_browser_settings_save),
        ("/allow/add", browser.api_browser_allowlist_add),
        ("/allow/remove", browser.api_browser_allowlist_remove),
        ("/reset", browser.api_browser_reset),
    ):
        app.add_url_rule(rule, rule, view, methods=["GET", "POST"])

    monkeypatch.setattr(runtime, "docker_available", lambda: True)
    monkeypatch.setattr(runtime, "running_container", lambda: None)
    monkeypatch.setattr(runtime, "_client", lambda: (_ for _ in ()).throw(RuntimeError("no docker in this test")))
    monkeypatch.setattr(runtime, "refresh_proxy", lambda: True)
    monkeypatch.setattr(host_shell, "read_config", lambda: {"user_password": bcrypt.hashpw(b"right", bcrypt.gensalt()), "2fa_enabled": False})

    return app.test_client()


def test_the_settings_endpoint_reports_values_ranges_allowlist_and_image(client):
    data = client.get("/settings").get_json()

    assert data["settings"] == settings.DEFAULTS
    assert data["ranges"]["memory_mb"] == [512, 16384]
    assert data["allowlist"] == []
    assert data["image"]["reference"] == runtime.engine().image_reference() and data["image"]["present"] is False


def test_saving_invalid_settings_says_which_field_and_why(client):
    response = client.post("/settings/save", json={"memory_mb": 10})

    assert response.status_code == 400
    assert response.get_json()["field"] == "memory_mb" and "between" in response.get_json()["error"]
    assert settings.load() == settings.DEFAULTS


def test_saving_valid_settings_persists_them(client):
    response = client.post("/settings/save", json={"idle_minutes": 20, "pids": 256})

    assert response.get_json()["settings"]["idle_minutes"] == 20
    assert settings.load()["pids"] == 256


def test_adding_an_entry_needs_the_password(client):
    for body in ({"entry": {"kind": "ip", "value": "10.0.0.5"}}, {"entry": {"kind": "ip", "value": "10.0.0.5"}, "password": "wrong"}):
        response = client.post("/allow/add", json=body)

        assert response.status_code == 401

    assert allowlist.entries() == []


def test_adding_an_entry_needs_2fa_when_it_is_on(client, monkeypatch):
    monkeypatch.setattr(host_shell, "read_config", lambda: {"user_password": bcrypt.hashpw(b"right", bcrypt.gensalt()), "2fa_enabled": True, "2fa_secret": "JBSWY3DPEHPK3PXP", "2fa_backup_codes": ""})

    response = client.post("/allow/add", json={"entry": {"kind": "ip", "value": "10.0.0.5"}, "password": "right", "code": "000000"})

    assert response.status_code == 401
    assert allowlist.entries() == []


def test_a_correct_password_adds_the_entry_audits_it_and_refreshes_the_proxy(client, monkeypatch, tmp_path):
    refreshed = []
    monkeypatch.setattr(runtime, "refresh_proxy", lambda: refreshed.append(True))

    response = client.post("/allow/add", json={"entry": {"kind": "subnet", "value": "192.168.1.0/24", "port": 443}, "password": "right"})

    assert response.status_code == 200
    assert [e["value"] for e in allowlist.entries()] == ["192.168.1.0/24"]
    assert refreshed == [True]

    (line,) = (tmp_path / "logs" / "browser.log").read_text().splitlines()
    fields = line.split("***")

    assert fields[1] == "allow-add" and "subnet 192.168.1.0/24:443" in fields[4]


def test_an_unsafe_entry_is_refused_even_with_the_right_password(client):
    response = client.post("/allow/add", json={"entry": {"kind": "ip", "value": "127.0.0.1"}, "password": "right"})

    assert response.status_code == 400 and response.get_json()["code"] == "invalid_entry"
    assert allowlist.entries() == []


def test_too_many_wrong_passwords_lock_the_gate(client):
    for _ in range(host_shell.MAX_AUTH_FAILURES):
        client.post("/allow/add", json={"entry": {"kind": "ip", "value": "10.0.0.5"}, "password": "wrong"})

    response = client.post("/allow/add", json={"entry": {"kind": "ip", "value": "10.0.0.5"}, "password": "right"})

    assert response.status_code == 429


def test_removing_an_entry_needs_no_password_and_is_audited(client, tmp_path):
    entry = allowlist.add({"kind": "ip", "value": "10.0.0.5"})

    response = client.post("/allow/remove", json={"id": entry["id"]})

    assert response.status_code == 200 and allowlist.entries() == []
    assert "allow-remove" in (tmp_path / "logs" / "browser.log").read_text()
    assert client.post("/allow/remove", json={"id": "nope"}).status_code == 404


def test_resetting_the_profile_needs_the_password(client, monkeypatch):
    deleted = []
    monkeypatch.setattr(runtime, "reset_profile", lambda: deleted.append(True))
    monkeypatch.setattr(runtime, "stop", lambda: None)

    assert client.post("/reset", json={}).status_code == 401
    assert client.post("/reset", json={"password": "wrong"}).status_code == 401
    assert deleted == []


def test_resetting_stops_the_browser_deletes_the_profile_and_is_audited(client, monkeypatch, tmp_path):
    order = []
    monkeypatch.setattr(runtime, "reset_profile", lambda: order.append("delete"))
    monkeypatch.setattr(runtime, "stop", lambda: order.append("stop"))
    monkeypatch.setattr(runtime, "status", lambda: {"phase": "stopped"})

    response = client.post("/reset", json={"password": "right"})

    assert response.status_code == 200
    assert order == ["stop", "delete"]
    assert "profile-reset" in (tmp_path / "logs" / "browser.log").read_text()


def test_the_profile_is_only_deleted_when_the_browser_is_gone(monkeypatch):
    removed = []
    volume = SimpleNamespace(remove=lambda force=False: removed.append(True))
    client = SimpleNamespace(containers=SimpleNamespace(get=lambda name: object()), volumes=SimpleNamespace(get=lambda name: volume))
    monkeypatch.setattr(runtime, "_client", lambda: client)

    with pytest.raises(runtime.BrowserError) as refused:
        runtime.reset_profile()

    assert refused.value.code == "still_running" and removed == []


def test_audit_lines_cannot_be_forged_through_a_field(tmp_path):
    allowlist.audit("allow-add", "1.2.3.4", "user\nforged***line", "ip 10.0.0.5")

    lines = (tmp_path / "logs" / "browser.log").read_text().splitlines()

    assert len(lines) == 1 and len(lines[0].split("***")) == 6

import pytest

from pymodules import hd_DomainStore as store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "domains_file", str(tmp_path / "domains.json"))
    monkeypatch.setattr(store, "reserved_hosts", lambda: {"homedock.local", "localhost", "192.168.1.5", "home.example.com"})
    store.reset_cache()


@pytest.mark.parametrize(
    "raw, expected",
    [("App.Example.com", "app.example.com"), ("app.example.com.", "app.example.com"), ("  blog.example.org ", "blog.example.org"), ("plex.homedock.local", "plex.homedock.local")],
)
def test_validate_accepts_and_normalizes(raw, expected):
    assert store.validate_fqdn(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "nodots", "10.0.0.1", "*.example.com", "a_b.example.com", "-a.example.com", "a..example.com", "foo.local", "foo.localhost", "foo.homedock.localhost", "homedock.local", "home.example.com", "x" * 64 + ".example.com", "localhost"],
)
def test_validate_rejects(raw):
    with pytest.raises(store.DomainError) as error:
        store.validate_fqdn(raw)

    assert error.value.status == 400


def test_add_domain_registers_app_and_slug():
    store.add_domain("My_App", "app.example.com", 80)

    app = store.get_app("My_App")

    assert app["slug"] == "my-app"
    assert app["domains"] == [{"fqdn": "app.example.com", "port": 80, "protocol": "auto", "path": "", "mode": "gated"}]


def test_slug_collision_gets_suffix():
    first = store.ensure_app("my.app")
    second = store.ensure_app("my_app")

    assert first["slug"] == "my-app"
    assert second["slug"] == "my-app-2"


def test_fqdn_is_unique_across_apps_and_names_owner():
    store.add_domain("one", "app.example.com", 80)

    with pytest.raises(store.DomainError) as error:
        store.add_domain("two", "APP.example.com", 80)

    assert error.value.status == 409
    assert "one" in error.value.message


def test_same_app_cannot_add_same_fqdn_twice():
    store.add_domain("one", "app.example.com", 80)

    with pytest.raises(store.DomainError) as error:
        store.add_domain("one", "app.example.com", 81)

    assert error.value.status == 409


@pytest.mark.parametrize("port", [0, 70000, "x", None, True])
def test_port_must_be_valid(port):
    with pytest.raises(store.DomainError) as error:
        store.add_domain("one", "app.example.com", port)

    assert error.value.status == 400


def test_protocol_path_and_mode_are_validated():
    store.add_domain("one", "a.example.com", 80, protocol="https", path="/admin/")

    assert store.get_app("one")["domains"][0]["protocol"] == "https"
    assert store.get_app("one")["domains"][0]["path"] == "/admin"

    for bad in ({"protocol": "ftp"}, {"path": "no-slash"}, {"path": "/a b"}, {"path": "/../x"}, {"mode": "direct"}, {"mode": "wat"}):
        with pytest.raises(store.DomainError):
            store.add_domain("one", "b.example.com", 80, **bad)


def test_primary_is_first_and_can_be_changed():
    store.add_domain("one", "a.example.com", 80)
    store.add_domain("one", "b.example.com", 80)

    assert [d["fqdn"] for d in store.get_app("one")["domains"]] == ["a.example.com", "b.example.com"]

    store.update_domain("one", "b.example.com", primary=True)

    assert [d["fqdn"] for d in store.get_app("one")["domains"]] == ["b.example.com", "a.example.com"]


def test_update_changes_fields():
    store.add_domain("one", "a.example.com", 80)

    store.update_domain("one", "a.example.com", port=8080, protocol="http", path="/x")

    assert store.get_app("one")["domains"][0] | {} == {"fqdn": "a.example.com", "port": 8080, "protocol": "http", "path": "/x", "mode": "gated"}


def test_remove_domain_and_unknown_cases():
    store.add_domain("one", "a.example.com", 80)

    store.remove_domain("one", "a.example.com")

    assert store.get_app("one")["domains"] == []

    with pytest.raises(store.DomainError) as error:
        store.remove_domain("one", "a.example.com")

    assert error.value.status == 404


def test_lookup_domain_and_slug():
    store.add_domain("one", "a.example.com", 8080)

    container, domain = store.lookup_domain("A.example.com")

    assert container == "one"
    assert domain["port"] == 8080
    assert store.lookup_domain("zzz.example.com") is None
    assert store.lookup_slug("one")[0] == "one"
    assert store.lookup_slug("nope") is None


def test_delete_app_removes_its_domains_so_they_can_be_reused():
    store.add_domain("one", "a.example.com", 80)

    store.delete_app("one")

    assert store.get_app("one") is None
    store.add_domain("two", "a.example.com", 80)


def test_web_port_override():
    store.ensure_app("one")

    store.set_web_port("one", 3000)
    assert store.get_app("one")["web_port"] == 3000

    store.set_web_port("one", None)
    assert store.get_app("one")["web_port"] is None


def test_persists_across_cache_reset():
    store.add_domain("one", "a.example.com", 80)
    store.reset_cache()

    assert store.get_app("one")["domains"][0]["fqdn"] == "a.example.com"


def test_reads_survive_a_corrupt_file(tmp_path):
    (tmp_path / "domains.json").write_text("{nope")
    store.reset_cache()

    assert store.get_app("one") is None

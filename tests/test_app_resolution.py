import pytest

from pymodules import hd_AppSubdomains as subdomains
from pymodules import hd_BackendResolver as resolver
from pymodules import hd_DomainStore as store
from pymodules import hd_RuntimeCompose as runtime


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    folder = tmp_path / "compose-link"
    folder.mkdir()
    (folder / "plex.yml").write_text("services:\n  plex:\n    container_name: plex\n    ports: ['32400:32400']\n")
    monkeypatch.setattr(resolver, "compose_folder", str(folder))
    monkeypatch.setattr(store, "domains_file", str(tmp_path / "domains.json"))
    monkeypatch.setattr(runtime, "suggested_port_for", lambda names: None)
    monkeypatch.setattr(subdomains, "get_desktop_hosts", lambda: {"localhost", "homedock.local", "dock.example.com"})
    monkeypatch.setattr(store, "reserved_hosts", lambda: {"localhost", "homedock.local", "dock.example.com"})
    store.reset_cache()
    resolver.reset_cache()


def test_exact_domain_resolves_to_its_container_and_port():
    store.add_domain("plex", "movies.other.org", 32400, path="/web")

    app = subdomains.resolve_app_for_host("Movies.other.org:8443")

    assert app["container"] == "plex"
    assert app["port"] == 32400
    assert app["trail"] == "web"
    assert app["implicit"] is False
    assert app["slug"] == "plex"


def test_window_route_resolves_under_the_current_host():
    app = subdomains.resolve_app_for_host("plex.dock.example.com")

    assert app["container"] == "plex"
    assert app["port"] == 32400
    assert app["implicit"] is True
    assert app["host_trail"] == "dock.example.com"


def test_domain_on_a_stopped_or_unrouted_app_still_resolves():
    store.add_domain("db", "db.other.org", 5432)

    assert subdomains.resolve_app_for_host("db.other.org")["container"] == "db"


def test_dashboard_hosts_never_resolve():
    assert subdomains.resolve_app_for_host("dock.example.com") is None
    assert subdomains.resolve_app_for_host("homedock.local") is None


def test_unknown_hosts_and_apps_do_not_resolve():
    assert subdomains.resolve_app_for_host("nothing.dock.example.com") is None
    assert subdomains.resolve_app_for_host("random.org") is None


def test_lan_domain_resolves_when_stored_but_window_route_on_local_does_not():
    assert subdomains.resolve_app_for_host("plex.homedock.local") is None

    store.add_domain("plex", "plex.homedock.local", 32400)

    assert subdomains.resolve_app_for_host("plex.homedock.local")["implicit"] is False


def test_namespace_check_is_unchanged():
    assert subdomains.is_app_namespace("zzz.dock.example.com") is True
    assert subdomains.is_app_namespace("random.org") is False

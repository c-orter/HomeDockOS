import pytest

from pymodules import hd_BackendResolver as resolver
from pymodules import hd_DomainStore as store
from pymodules import hd_RuntimeCompose as runtime


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    folder = tmp_path / "compose-link"
    folder.mkdir()
    monkeypatch.setattr(resolver, "compose_folder", str(folder))
    monkeypatch.setattr(store, "domains_file", str(tmp_path / "domains.json"))
    monkeypatch.setattr(store, "reserved_hosts", lambda: set())
    monkeypatch.setattr(runtime, "suggested_port_for", lambda names: None)
    store.reset_cache()
    resolver.reset_cache()

    return folder


def write(folder, name, text):
    (folder / f"{name}.yml").write_text(text)
    resolver.reset_cache()


WEB = "services:\n  web:\n    container_name: web\n    ports: ['8080:80', '53:53/udp']\n  db:\n    container_name: web-db\n    ports: ['5432:5432']\n"


def test_default_web_port_is_first_tcp_port_of_the_owning_service(isolated):
    write(isolated, "web", WEB)

    assert resolver.web_port("web") == 80
    assert resolver.web_port("web-db") is None


def test_web_port_override_wins(isolated):
    write(isolated, "web", WEB)
    store.set_web_port("web-db", 5432)

    assert resolver.web_port("web-db") == 5432
    assert resolver.web_port("web") is None


def test_container_mode_uses_container_name(isolated, monkeypatch):
    monkeypatch.setattr(resolver, "is_docker", True)
    write(isolated, "web", WEB)

    assert resolver.resolve_backend("web", 80) == ("web", 80)


def test_host_network_uses_docker_host(isolated, monkeypatch):
    monkeypatch.setattr(resolver, "is_docker", True)
    monkeypatch.setattr(resolver, "docker_host", "host.docker.internal")
    write(isolated, "ha", "services:\n  ha:\n    container_name: ha\n    network_mode: host\n")

    assert resolver.resolve_backend("ha", 8123) == ("host.docker.internal", 8123)


def test_native_mode_uses_published_port(isolated, monkeypatch):
    monkeypatch.setattr(resolver, "is_docker", False)
    monkeypatch.setattr(resolver, "docker_host", "localhost")
    write(isolated, "web", WEB)

    assert resolver.resolve_backend("web", 80) == ("localhost", 8080)


def test_sync_registers_installed_containers_with_slugs(isolated):
    write(isolated, "web", WEB)

    resolver.sync_installed_apps()

    assert store.get_app("web")["slug"] == "web"
    assert store.get_app("web-db")["slug"] == "web-db"

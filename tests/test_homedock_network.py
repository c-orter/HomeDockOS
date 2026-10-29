import docker

from pymodules import hd_HomedockNetwork as module


class FakeNetwork:
    def __init__(self, name):
        self.name = name
        self.connected = []

    def connect(self, container):
        if container in self.connected:
            raise docker.errors.APIError("endpoint with name x already exists in network homedock_network")
        self.connected.append(container)


class FakeNetworks:
    def __init__(self, existing=()):
        self.items = {n: FakeNetwork(n) for n in existing}
        self.created = []

    def list(self, names=None):
        return [n for k, n in self.items.items() if not names or k in names]

    def create(self, name, driver):
        self.created.append((name, driver))
        self.items[name] = FakeNetwork(name)
        return self.items[name]


class FakeContainers:
    def __init__(self, names):
        self.names = names

    def get(self, ref):
        if ref not in self.names:
            raise docker.errors.NotFound("no such container")
        return ref


class FakeClient:
    def __init__(self, networks, containers):
        self.networks = networks
        self.containers = containers


def test_creates_network_when_missing_and_reuses_it_when_present():
    client = FakeClient(FakeNetworks(), FakeContainers([]))

    first = module.ensure_network(client)
    second = module.ensure_network(client)

    assert first is second
    assert client.networks.created == [(module.NETWORK, "bridge")]


def test_join_self_uses_hostname_then_falls_back_to_container_name(monkeypatch):
    monkeypatch.setattr(module.socket, "gethostname", lambda: "abc123")
    client = FakeClient(FakeNetworks(), FakeContainers(["homedock-os"]))

    assert module.join_self(client) is True
    assert client.networks.items[module.NETWORK].connected == ["homedock-os"]


def test_join_is_idempotent(monkeypatch):
    monkeypatch.setattr(module.socket, "gethostname", lambda: "abc123")
    client = FakeClient(FakeNetworks(), FakeContainers(["abc123"]))

    assert module.join_self(client) is True
    assert module.join_self(client) is True
    assert client.networks.items[module.NETWORK].connected == ["abc123"]


def test_join_self_reports_false_when_own_container_unknown(monkeypatch):
    monkeypatch.setattr(module.socket, "gethostname", lambda: "abc123")
    client = FakeClient(FakeNetworks(), FakeContainers([]))

    assert module.join_self(client) is False


def test_connect_apps_joins_existing_containers_and_skips_missing_and_host_mode(tmp_path):
    (tmp_path / "web.yml").write_text("services:\n  web:\n    container_name: web\n  db:\n    container_name: web-db\n  gone:\n    container_name: gone\n  host:\n    container_name: hostapp\n    network_mode: host\n")
    client = FakeClient(FakeNetworks(), FakeContainers(["web", "web-db", "hostapp"]))

    module.connect_apps(client, str(tmp_path))

    assert client.networks.items[module.NETWORK].connected == ["web", "web-db"]


def test_podman_style_already_connected_error_is_ignored():
    class PodmanNetwork:
        def connect(self, container):
            raise docker.errors.APIError("container x is already connected to network homedock_network: network is already connected")

    module._connect(PodmanNetwork(), "x")

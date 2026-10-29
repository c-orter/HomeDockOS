import threading

from pymodules import hd_PortDiscovery as discovery


class FakeContainer:
    def __init__(self, ports):
        self.attrs = {"NetworkSettings": {"Ports": ports}}

    def reload(self):
        pass


class FakeContainers:
    def __init__(self):
        self.items = {}
        self.gets = 0

    def get(self, name):
        self.gets += 1

        if name not in self.items:
            raise discovery.docker.errors.NotFound("gone")

        return self.items[name]


class FakeClient:
    def __init__(self, events=()):
        self.containers = FakeContainers()
        self._events = list(events)

    def events(self, decode=True, filters=None):
        return iter(self._events)


def setup_function():
    discovery.reset()


def teardown_function():
    discovery.reset()


def test_extracts_tcp_host_ports_only():
    attrs = {"NetworkSettings": {"Ports": {"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "49153"}], "53/udp": [{"HostPort": "5353"}], "22/tcp": None}}}

    assert discovery.extract_ports(attrs) == {80: 49153}


def test_published_port_inspects_once_then_serves_the_cache():
    client = FakeClient()
    client.containers.items["web"] = FakeContainer({"80/tcp": [{"HostPort": "49153"}]})

    assert discovery.published_port("web", 80, client) == 49153
    assert discovery.published_port("web", 80, client) == 49153
    assert client.containers.gets == 1


def test_unknown_or_stopped_container_gives_none_and_is_not_cached_as_a_hit():
    client = FakeClient()

    assert discovery.published_port("web", 80, client) is None

    client.containers.items["web"] = FakeContainer({"80/tcp": [{"HostPort": "49200"}]})

    assert discovery.published_port("web", 80, client) == 49200


def test_start_event_refreshes_and_die_forgets():
    client = FakeClient(
        events=[
            {"Action": "start", "Actor": {"Attributes": {"name": "web"}}},
            {"Action": "die", "Actor": {"Attributes": {"name": "other"}}},
        ]
    )
    client.containers.items["web"] = FakeContainer({"80/tcp": [{"HostPort": "49300"}]})
    discovery._cache["other"] = {80: 1}

    discovery.watch_events(client, threading.Event())

    assert discovery._cache["web"] == {80: 49300}
    assert "other" not in discovery._cache


def test_restart_picks_up_the_new_port():
    client = FakeClient(events=[{"Action": "start", "Actor": {"Attributes": {"name": "web"}}}])
    client.containers.items["web"] = FakeContainer({"80/tcp": [{"HostPort": "49400"}]})
    discovery._cache["web"] = {80: 49153}

    discovery.watch_events(client, threading.Event())

    assert discovery.published_port("web", 80, client) == 49400

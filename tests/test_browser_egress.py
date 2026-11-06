import asyncio

import pytest

from pymodules import hd_BrowserEgressProxy as proxy


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1", "127.255.255.254", "0.0.0.0", "10.0.0.1", "172.16.0.1", "172.31.255.255", "192.168.1.1",
        "169.254.169.254", "169.254.0.1", "100.64.0.1", "100.127.255.255", "192.0.0.1", "198.18.0.1", "224.0.0.1",
        "240.0.0.1", "255.255.255.255",
        "::1", "::", "fe80::1", "fc00::1", "fd00:ec2::254", "fec0::1", "ff02::1",
        "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254", "::ffff:192.168.0.1", "::ffff:7f00:1",
        "64:ff9b::7f00:1", "64:ff9b::a00:1", "2002:7f00:1::", "2002:a00:1::", "2001:0:4136:e378:8000:63bf:3fff:fdd2",
        "::127.0.0.1", "100::1",
        "not an address", "", "999.1.1.1", "1.2.3",
    ],
)
def test_private_and_odd_addresses_are_refused(address):
    assert proxy.is_public(address) is False


@pytest.mark.parametrize("address", ["1.1.1.1", "8.8.8.8", "93.184.216.34", "172.32.0.1", "100.63.255.255", "2606:4700:4700::1111", "2001:4860:4860::8888", "::ffff:8.8.8.8"])
def test_public_addresses_are_allowed(address):
    assert proxy.is_public(address) is True


def run(coro):
    return asyncio.run(coro)


class Loop:
    def __init__(self, answers):
        self.answers = answers

    async def getaddrinfo(self, host, port, type=0):
        return [(0, 0, 0, "", (a, port)) for a in self.answers]


def test_a_public_name_resolves_to_its_address():
    assert run(proxy.resolve("example.com", 443, Loop(["93.184.216.34"]))) == "93.184.216.34"


def test_a_public_name_that_points_at_a_private_address_is_refused():
    with pytest.raises(proxy.Refused) as refused:
        run(proxy.resolve("sneaky.example", 443, Loop(["10.0.0.5"])))

    assert refused.value.status == 403


def test_one_private_answer_among_public_ones_refuses_the_name():
    with pytest.raises(proxy.Refused):
        run(proxy.resolve("mixed.example", 80, Loop(["93.184.216.34", "127.0.0.1"])))


def test_the_connection_goes_to_the_checked_address():
    assert run(proxy.resolve("example.com", 80, Loop(["1.1.1.1", "8.8.8.8"]))) == "1.1.1.1"


def test_an_address_literal_is_checked_without_a_lookup():
    with pytest.raises(proxy.Refused):
        run(proxy.resolve("127.0.0.1", 80, Loop([])))

    with pytest.raises(proxy.Refused):
        run(proxy.resolve("[::1]", 80, Loop([])))

    assert run(proxy.resolve("1.1.1.1", 80, Loop([]))) == "1.1.1.1"


def test_an_unresolvable_name_is_a_bad_gateway():
    with pytest.raises(proxy.Refused) as refused:
        run(proxy.resolve("nope.invalid", 80, Loop([])))

    assert refused.value.status == 502


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_impossible_ports_are_refused(port):
    with pytest.raises(proxy.Refused):
        run(proxy.resolve("1.1.1.1", port, Loop([])))


def test_destinations_are_parsed():
    assert proxy.split_hostport("example.com:8443", 443) == ("example.com", 8443)
    assert proxy.split_hostport("example.com", 443) == ("example.com", 443)
    assert proxy.split_hostport("[::1]:80", 443) == ("::1", 80)
    assert proxy.split_hostport("[2606:4700::1111]", 443) == ("2606:4700::1111", 443)

    with pytest.raises(proxy.Refused):
        proxy.split_hostport("example.com:abc", 443)


def test_a_plain_request_is_rewritten_for_the_origin_and_loses_proxy_headers():
    method, target, version, headers = proxy.parse_head(b"GET http://example.com:8080/a?b=1 HTTP/1.1\r\nHost: example.com:8080\r\nProxy-Connection: keep-alive\r\nProxy-Authorization: x\r\nConnection: keep-alive\r\nAccept: */*")
    host, port, path = proxy.destination(method, target, headers)

    assert (host, port, path) == ("example.com", 8080, "/a?b=1")

    head = proxy.forward_head(method, path, version, headers).decode()

    assert head.startswith("GET /a?b=1 HTTP/1.1\r\n")
    assert "Proxy-" not in head
    assert head.lower().count("connection:") == 1 and "Connection: close" in head
    assert head.endswith("\r\n\r\n")


def test_origin_form_requests_are_not_proxy_requests():
    with pytest.raises(proxy.Refused):
        proxy.destination("GET", "/just/a/path", [])

    with pytest.raises(proxy.Refused):
        proxy.parse_head(b"nonsense")


async def exchange(payload, allow_loopback=False, answers=None):
    """Runs one request through a live proxy and returns what the client got back."""

    seen = []

    async def origin(reader, writer):
        seen.append(await reader.read(65536))
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        await writer.drain()
        writer.close()

    origin_server = await asyncio.start_server(origin, "127.0.0.1", 0)
    origin_port = origin_server.sockets[0].getsockname()[1]

    server = await asyncio.start_server(proxy.handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(payload(origin_port))
    await writer.drain()
    reply = await asyncio.wait_for(reader.read(65536), 5)
    writer.close()
    server.close()
    origin_server.close()

    return reply, seen


@pytest.fixture
def loopback_is_public(monkeypatch):
    """Only so a local stand-in origin can be reached; the refusal tests below leave the real rule in place."""

    monkeypatch.setattr(proxy, "is_public", lambda a: True)


def test_a_request_to_a_private_address_gets_a_403_and_never_connects():
    reply, seen = run(exchange(lambda p: f"GET http://127.0.0.1:{p}/ HTTP/1.1\r\nHost: x\r\n\r\n".encode()))

    assert reply.startswith(b"HTTP/1.1 403")
    assert seen == []


def test_a_tunnel_to_a_private_address_gets_a_403_and_never_connects():
    reply, seen = run(exchange(lambda p: f"CONNECT 127.0.0.1:{p} HTTP/1.1\r\nHost: x\r\n\r\n".encode()))

    assert reply.startswith(b"HTTP/1.1 403")
    assert seen == []


def test_a_proxied_request_reaches_a_public_origin(loopback_is_public):
    reply, seen = run(exchange(lambda p: f"GET http://127.0.0.1:{p}/x HTTP/1.1\r\nHost: x\r\nProxy-Connection: keep-alive\r\n\r\n".encode()))

    assert reply.endswith(b"ok")
    assert seen[0].startswith(b"GET /x HTTP/1.1\r\n") and b"Proxy-" not in seen[0]


def test_a_tunnel_carries_bytes_both_ways(loopback_is_public):
    def payload(p):
        return f"CONNECT 127.0.0.1:{p} HTTP/1.1\r\nHost: x\r\n\r\nping".encode()

    reply, seen = run(exchange(payload))

    assert reply.startswith(b"HTTP/1.1 200 Connection established")
    assert seen == [b"ping"]

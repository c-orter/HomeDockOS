"""
hd_BrowserEgressProxy.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro

The browser's only way out. This file is copied into a small proxy container and run there (python only, standard
library only, so the container needs nothing installed). HomeDock also imports it to test the address rules.

It forwards HTTP and HTTPS (CONNECT) and refuses any destination that is not a public internet address. The name is
resolved here, every answer is checked, and the connection goes to the checked address itself, so a name that
resolves to a private address, or changes its answer between a check and a connection, cannot get past it.
"""

import asyncio
import ipaddress
import json
import os
import socket
import sys
from urllib.parse import urlsplit

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 3128

MAX_HEAD = 64 * 1024
MAX_CONNECTIONS = 512
CONNECT_TIMEOUT = 10
IDLE_TIMEOUT = 300

# Ranges that are not reachable on the public internet but that Python's is_global does not always reject across
# versions, or that smuggle an IPv4 address inside an IPv6 one. Refused outright.
_EXTRA_BLOCKED = tuple(
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "100.64.0.0/10",
        "192.0.0.0/24",
        "192.88.99.0/24",
        "198.18.0.0/15",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::/96",
        "64:ff9b::/96",
        "64:ff9b:1::/48",
        "2001::/32",
        "2002::/16",
        "100::/64",
        "fc00::/7",
        "fe80::/10",
        "fec0::/10",
        "ff00::/8",
    )
)


def is_public(address):
    """True only for an address on the public internet. Anything unparseable is refused."""

    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False

    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    if not ip.is_global:
        return False

    return not any(ip in net for net in _EXTRA_BLOCKED if net.version == ip.version)


class Refused(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status
        self.reason = reason


# Never opened by an allowlist entry, whatever it says: this machine itself, link-local (cloud metadata lives there),
# multicast and the unspecified address.
_NEVER_ALLOWED = tuple(ipaddress.ip_network(n) for n in ("0.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16", "224.0.0.0/4", "255.255.255.255/32", "::/128", "::1/128", "fe80::/10", "ff00::/8"))

# The container engine's own network API. Never reachable through an allowlist entry.
_NEVER_PORTS = (2375, 2376)


def _unmapped(address):
    ip = ipaddress.ip_address(address)

    return ip.ipv4_mapped if ip.version == 6 and ip.ipv4_mapped is not None else ip


class Rules:
    """What the admin opened (allow) and what stays shut regardless (deny). Both empty by default, so only the public internet is reachable."""

    def __init__(self, allow=(), deny=()):
        self.allow = []
        self.deny = []

        for entry in allow:
            net = ipaddress.ip_network(entry["net"], strict=False) if entry.get("net") else None
            host = str(entry["host"]).lower() if entry.get("host") else None

            if net is not None or host is not None:
                self.allow.append({"net": net, "host": host, "port": int(entry["port"]) if entry.get("port") else None})

        for entry in deny:
            self.deny.append(ipaddress.ip_network(entry, strict=False))

    @classmethod
    def from_env(cls, environ=None):
        raw = (environ if environ is not None else os.environ).get("HD_EGRESS_RULES", "")

        if not raw:
            return cls()

        try:
            data = json.loads(raw)

            return cls(data.get("allow", []), data.get("deny", []))
        except (ValueError, KeyError, TypeError, AttributeError):
            print("egress proxy: ignoring unreadable rules; only the public internet is reachable", file=sys.stderr)

            return cls()

    def denied(self, address):
        ip = _unmapped(address)

        return any(ip in net for net in self.deny if net.version == ip.version)

    def permits(self, host, address, port):
        """True when an entry opens this exact destination, and it is not one that can never be opened."""

        ip = _unmapped(address)

        if port in _NEVER_PORTS or any(ip in net for net in _NEVER_ALLOWED if net.version == ip.version):
            return False

        name = host.strip("[]").lower()

        for entry in self.allow:
            if entry["port"] is not None and entry["port"] != port:
                continue

            if entry["net"] is not None and entry["net"].version == ip.version and ip in entry["net"]:
                return True

            if entry["host"] is not None and entry["host"] == name:
                return True

        return False


RULES = Rules()


async def resolve(host, port, loop=None, rules=None):
    """The checked address to connect to. Every answer for the name must be public, or be opened by an allowlist entry, and none may be on the deny list; otherwise the name is refused."""

    rules = rules or RULES

    if not 0 < port < 65536:
        raise Refused(403, "Port not allowed")

    host = host.strip("[]")

    try:
        ipaddress.ip_address(host)
        answers = [host]
    except ValueError:
        loop = loop or asyncio.get_running_loop()

        try:
            infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError:
            raise Refused(502, "Could not resolve the name")

        answers = []

        for info in infos:
            if info[4][0] not in answers:
                answers.append(info[4][0])

    if not answers:
        raise Refused(502, "Could not resolve the name")

    for address in answers:
        try:
            if rules.denied(address):
                raise Refused(403, "Destination is not allowed")
        except ValueError:
            raise Refused(403, "Destination is not a public internet address")

        if not is_public(address) and not rules.permits(host, address, port):
            raise Refused(403, "Destination is not a public internet address")

    return answers[0]


def split_hostport(text, default_port):
    text = text.strip()

    if text.startswith("["):
        host, _, rest = text[1:].partition("]")
        port = rest[1:] if rest.startswith(":") else ""
    elif text.count(":") == 1:
        host, _, port = text.partition(":")
    else:
        host, port = text, ""

    if not host:
        raise Refused(400, "Bad destination")

    try:
        return host, int(port) if port else default_port
    except ValueError:
        raise Refused(400, "Bad destination")


def parse_head(raw):
    """(method, target, version, header_lines) from a request head."""

    lines = raw.decode("latin-1").split("\r\n")
    parts = lines[0].split(" ")

    if len(parts) != 3 or not parts[2].startswith("HTTP/"):
        raise Refused(400, "Bad request")

    return parts[0], parts[1], parts[2], [h for h in lines[1:] if h]


def destination(method, target, headers):
    """(host, port, origin_form_target) for a request."""

    if method == "CONNECT":
        host, port = split_hostport(target, 443)

        return host, port, None

    split = urlsplit(target)

    if split.scheme == "http" and split.hostname:
        port = split.port or 80
        path = (split.path or "/") + (f"?{split.query}" if split.query else "")

        return split.hostname, port, path

    raise Refused(400, "Only proxied requests are accepted")


def forward_head(method, path, version, headers):
    kept = [h for h in headers if h.split(":", 1)[0].strip().lower() not in ("proxy-connection", "proxy-authorization", "connection")]
    kept.append("Connection: close")

    return ("\r\n".join([f"{method} {path} {version}", *kept]) + "\r\n\r\n").encode("latin-1")


async def _pipe(reader, writer):
    try:
        while True:
            chunk = await asyncio.wait_for(reader.read(65536), IDLE_TIMEOUT)

            if not chunk:
                break

            writer.write(chunk)
            await writer.drain()
    except (asyncio.TimeoutError, ConnectionError, OSError):
        pass
    finally:
        try:
            writer.close()
        except OSError:
            pass


async def _reply(writer, status, reason):
    body = (reason + "\n").encode("utf-8")
    head = f"HTTP/1.1 {status} {reason}\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"

    try:
        writer.write(head.encode("latin-1") + body)
        await writer.drain()
    except (ConnectionError, OSError):
        pass


async def handle(reader, writer):
    upstream = None

    try:
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), CONNECT_TIMEOUT)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
            return

        try:
            method, target, version, headers = parse_head(raw[:-4])
            host, port, path = destination(method, target, headers)
            address = await resolve(host, port)

            try:
                upstream = await asyncio.wait_for(asyncio.open_connection(address, port), CONNECT_TIMEOUT)
            except (asyncio.TimeoutError, OSError):
                raise Refused(502, "Could not connect")
        except Refused as e:
            await _reply(writer, e.status, e.reason)
            return

        up_reader, up_writer = upstream

        if method == "CONNECT":
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
        else:
            up_writer.write(forward_head(method, path, version, headers))
            await up_writer.drain()

        await asyncio.gather(_pipe(reader, up_writer), _pipe(up_reader, writer))
    finally:
        for w in (writer, upstream[1] if upstream else None):
            if w is not None:
                try:
                    w.close()
                except OSError:
                    pass


async def serve():
    gate = asyncio.Semaphore(MAX_CONNECTIONS)

    async def guarded(reader, writer):
        async with gate:
            await handle(reader, writer)

    server = await asyncio.start_server(guarded, LISTEN_HOST, int(os.environ.get("PORT", LISTEN_PORT)), limit=MAX_HEAD)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    RULES = Rules.from_env()

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        sys.exit(0)

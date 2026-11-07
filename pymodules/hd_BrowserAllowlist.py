"""
hd_BrowserAllowlist.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro

The list of private destinations the admin has opened to the browser. Empty by default: the browser reaches only the
public internet. The egress proxy enforces the list; this module stores it, checks what may be added, and builds the
rules the proxy is started with.
"""

import ipaddress
import json
import os
import re
import secrets
import tempfile
import threading
import time
from datetime import datetime

from pymodules.hd_BrowserSettings import BROWSER_FOLDER
from pymodules.hd_FunctionsGlobals import current_directory

ALLOWLIST_FILE = os.path.join(BROWSER_FOLDER, "allowlist.json")
AUDIT_FILE = os.path.join(current_directory, "logs", "browser.log")

KINDS = ("host", "ip", "subnet", "app")

MAX_ENTRIES = 100

# A broader range than this is a mistake, not a LAN.
MIN_PREFIX = {4: 8, 6: 32}

# Entries can never open these, and the proxy checks the same list on every request.
NEVER = tuple(ipaddress.ip_network(n) for n in ("0.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16", "224.0.0.0/4", "255.255.255.255/32", "::/128", "::1/128", "fe80::/10", "ff00::/8"))
NEVER_PORTS = (2375, 2376)

_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?)*$")
_CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

_lock = threading.Lock()
_audit_lock = threading.Lock()


class AllowlistError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _port(value):
    if value in (None, "", 0):
        return None

    if isinstance(value, bool):
        raise AllowlistError("The port must be a number between 1 and 65535.")

    try:
        port = int(value)
    except (TypeError, ValueError):
        raise AllowlistError("The port must be a number between 1 and 65535.")

    if not 1 <= port <= 65535:
        raise AllowlistError("The port must be a number between 1 and 65535.")

    if port in NEVER_PORTS:
        raise AllowlistError(f"Port {port} is the container engine's own API and can never be opened.")

    return port


def parse_entry(raw):
    """A clean entry {kind, value, port}, or AllowlistError saying what is wrong."""

    if not isinstance(raw, dict):
        raise AllowlistError("Send the entry as an object.")

    kind = raw.get("kind")
    value = str(raw.get("value", "")).strip()
    port = _port(raw.get("port"))

    if kind not in KINDS:
        raise AllowlistError("Choose host, IP address, subnet or app.")

    if not value:
        raise AllowlistError("Enter what to allow.")

    if kind == "ip":
        try:
            ip = ipaddress.ip_address(value)
        except ValueError:
            raise AllowlistError("That is not an IP address.")

        if any(ip in net for net in NEVER if net.version == ip.version):
            raise AllowlistError("That address belongs to this machine itself, or is link-local or multicast, and can never be opened.")

        value = str(ip)

    elif kind == "subnet":
        try:
            net = ipaddress.ip_network(value, strict=False)
        except ValueError:
            raise AllowlistError("That is not a subnet. Use a form like 192.168.1.0/24.")

        if net.prefixlen < MIN_PREFIX[net.version]:
            raise AllowlistError(f"That range is too wide. Use /{MIN_PREFIX[net.version]} or narrower.")

        if any(net.overlaps(never) for never in NEVER if never.version == net.version):
            raise AllowlistError("That range includes addresses that can never be opened (this machine itself, link-local, multicast).")

        value = str(net)

    elif kind == "host":
        if not _HOST.match(value) or len(value) > 253:
            raise AllowlistError("That is not a valid host name. Wildcards are not allowed.")

        if value.lower() in ("localhost", "localhost.localdomain"):
            raise AllowlistError("localhost is this machine itself and can never be opened.")

        value = value.lower()

    elif kind == "app":
        if not _CONTAINER.match(value):
            raise AllowlistError("That is not a valid app name.")

    return {"kind": kind, "value": value, "port": port}


def _read():
    try:
        with open(ALLOWLIST_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []

    entries = []

    for item in data.get("entries", []) if isinstance(data, dict) else []:
        try:
            entry = parse_entry(item)
            entry.update(id=str(item["id"]), added=item.get("added", 0))
            entries.append(entry)
        except (AllowlistError, KeyError, TypeError):
            continue

    return entries


def _write(entries):
    os.makedirs(BROWSER_FOLDER, mode=0o700, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=BROWSER_FOLDER, prefix=".allowlist.")

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"entries": entries}, handle)

        os.replace(temporary, ALLOWLIST_FILE)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass

        raise


def entries():
    with _lock:
        return _read()


def add(raw):
    """Stores a new entry (or returns the identical one already there). Callers must have checked fresh authentication first."""

    clean = parse_entry(raw)

    with _lock:
        current = _read()

        for existing in current:
            if (existing["kind"], existing["value"], existing["port"]) == (clean["kind"], clean["value"], clean["port"]):
                return existing

        if len(current) >= MAX_ENTRIES:
            raise AllowlistError(f"The allowlist is full ({MAX_ENTRIES} entries). Remove one first.")

        clean.update(id=secrets.token_hex(8), added=int(time.time()))
        current.append(clean)
        _write(current)

    return clean


def remove(entry_id):
    """Removing never needs more than a login: it only closes things."""

    with _lock:
        current = _read()
        kept = [e for e in current if e["id"] != entry_id]

        if len(kept) == len(current):
            return None

        _write(kept)

    return next(e for e in current if e["id"] == entry_id)


def describe(entry):
    return f"{entry['kind']} {entry['value']}" + (f":{entry['port']}" if entry["port"] else "")


def proxy_rules(deny_addresses=()):
    """The rules the egress proxy is started with."""

    allow = []

    for entry in entries():
        item = {"port": entry["port"]}

        if entry["kind"] in ("ip", "subnet"):
            item["net"] = entry["value"]
        else:
            item["host"] = entry["value"]

        allow.append(item)

    return {"allow": allow, "deny": sorted({str(a) for a in deny_addresses})}


def has_apps():
    return any(e["kind"] == "app" for e in entries())


def audit(event, ip, user, target, detail=""):
    """One line per change: when, what, who, from where."""

    from pymodules.hd_HostShell import clean_field

    line = "***".join([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), clean_field(event), clean_field(ip), clean_field(user), clean_field(target), clean_field(detail)])

    try:
        with _audit_lock:
            os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)

            with open(AUDIT_FILE, "a") as handle:
                handle.write(line + "\n")
    except OSError:
        pass

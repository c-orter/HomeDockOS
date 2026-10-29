"""
hd_CertPlan.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import socket

from pymodules.hd_AcmeCredentials import match_credential, load_credentials
from pymodules.hd_DomainStore import list_apps, LAN_SUFFIX

# Let's Encrypt allows 100 names on one certificate
MAX_NAMES = 100


def _local_addresses():
    found = set()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass

    return found


def server_addresses():
    from pymodules.hd_FunctionsNetwork import get_internet_ip, get_local_ip

    addresses = _local_addresses()

    for finder in (get_internet_ip, get_local_ip):
        try:
            addresses.add(finder())
        except Exception:
            pass

    addresses.discard("127.0.0.1")

    return addresses


def resolve_a(name):
    from pymodules.hd_DNSProbe import PUBLIC_RESOLVERS, TYPE_A, _first_answer

    return _first_answer(PUBLIC_RESOLVERS, name, TYPE_A)


def resolves_to_server(name, resolver=resolve_a, addresses=None):
    """Returns (ok, reason). Only the DNS side can be checked here; an http-01 order is the real test of port 80."""

    answers = resolver(name)

    if not answers:
        return False, "its DNS name does not resolve"

    mine = server_addresses() if addresses is None else addresses

    if not mine.intersection(answers):
        return False, f"its DNS points at {', '.join(sorted(answers))}, not at this server"

    return True, ""


def stored_names():
    names = []

    for app in list_apps().values():
        for domain in app.get("domains", []):
            if domain["fqdn"] not in names:
                names.append(domain["fqdn"])

    return names


def _under_wildcard(name, base):
    return name.endswith("." + base) and "." not in name[: -len(base) - 1]


def plan_names(base, names=None, entries=None, resolver=resolve_a, addresses=None):
    """Which names go on the certificate: the base, its wildcard, and each other stored name that passes the pre-check.

    Returns {"covered": [...], "excluded": [{"name", "reason"}], "challenges": {name: "dns-01" | "http-01"}}; wildcards are always dns-01.
    """

    base = (base or "").strip().lower().rstrip(".")
    entries = load_credentials() if entries is None else entries
    names = stored_names() if names is None else names

    covered = []
    excluded = []
    challenges = {}

    if not base:
        return {"covered": covered, "excluded": excluded, "challenges": challenges}

    if match_credential(base, entries) is None:
        excluded.append({"name": base, "reason": "no DNS provider covers the base domain"})
        excluded.append({"name": f"*.{base}", "reason": "no DNS provider covers the base domain"})
    else:
        for name in (base, f"*.{base}"):
            covered.append(name)
            challenges[name] = "dns-01"

    for name in names:
        name = (name or "").strip().lower().rstrip(".")

        if not name or name in covered or name in (item["name"] for item in excluded):
            continue

        if name == base or (_under_wildcard(name, base) and f"*.{base}" in covered):
            continue

        if name.endswith(LAN_SUFFIX) or name.endswith(".local") or name.endswith(".localhost"):
            excluded.append({"name": name, "reason": "local names cannot get a public certificate"})
            continue

        ok, reason = resolves_to_server(name, resolver, addresses)

        if not ok:
            excluded.append({"name": name, "reason": reason})
            continue

        if len(covered) >= MAX_NAMES:
            excluded.append({"name": name, "reason": f"a certificate holds at most {MAX_NAMES} names"})
            continue

        covered.append(name)

        # no provider covers the zone, so port 80 has to answer for it
        challenges[name] = "dns-01" if match_credential(name, entries) else "http-01"

    return {"covered": covered, "excluded": excluded, "challenges": challenges}

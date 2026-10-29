"""
hd_AcmeCredentials.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import os
import json
import threading

from pymodules.hd_FunctionsGlobals import user_packages_acme_folder
from pymodules.hd_FunctionsConfig import read_config
from pymodules.hd_ACMEProviders import PROVIDERS

CREDENTIALS_FILE = os.path.join(user_packages_acme_folder, "credentials.json")

# these providers can only publish a TXT record on their own zone name, so they cannot answer for a name below it
EXACT_ZONE_ONLY = {"freemyip", "duckdns"}

_lock = threading.RLock()


class CredentialError(Exception):
    pass


def _clean_zone(zone):
    return (zone or "").strip().lower().rstrip(".")


def _read_file():
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None

    if not isinstance(data, list):
        return None

    return [entry for entry in data if isinstance(entry, dict) and entry.get("zone") and entry.get("provider") and entry.get("token")]


def _write_file(entries):
    os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)

    temporary = f"{CREDENTIALS_FILE}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)

    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, indent=2)

    os.replace(temporary, CREDENTIALS_FILE)


def _legacy_entry():
    """The single provider and token the settings used to hold, as the base domain's entry."""

    config = read_config()

    zone = _clean_zone(config.get("base_domain"))
    provider = (config.get("acme_provider") or "").strip().lower()
    token = config.get("acme_token") or ""

    if zone and provider and token:
        return {"zone": zone, "provider": provider, "token": token}

    return None


def load_credentials():
    """The credential list; the first read after an upgrade migrates the old global pair in as the base domain's entry."""

    with _lock:
        entries = _read_file()

        if entries is None:
            legacy = _legacy_entry()
            entries = [legacy] if legacy else []

            if os.path.isfile(CREDENTIALS_FILE) or entries:
                _write_file(entries)

        return entries


def public_credentials():
    """The list without tokens, safe to send to the browser."""

    return [{"zone": entry["zone"], "provider": entry["provider"]} for entry in load_credentials()]


def set_credential(zone, provider, token):
    zone = _clean_zone(zone)
    provider = (provider or "").strip().lower()

    if not zone or "." not in zone:
        raise CredentialError("A zone such as example.com is required.")

    if provider not in PROVIDERS:
        raise CredentialError(f"Unknown DNS provider: {provider}")

    if not token:
        raise CredentialError("A DNS provider token is required.")

    with _lock:
        entries = [entry for entry in load_credentials() if entry["zone"] != zone]
        entries.append({"zone": zone, "provider": provider, "token": token})

        _write_file(entries)


def remove_credential(zone):
    zone = _clean_zone(zone)

    with _lock:
        entries = load_credentials()
        kept = [entry for entry in entries if entry["zone"] != zone]

        if len(kept) == len(entries):
            return False

        _write_file(kept)

        return True


def stored_token(zone, provider):
    """The token saved for this zone, only when it belongs to the same provider."""

    zone = _clean_zone(zone)

    for entry in load_credentials():
        if entry["zone"] == zone and entry["provider"] == (provider or "").strip().lower():
            return entry["token"]

    return ""


def match_credential(name, entries=None):
    """The entry whose zone is the longest suffix of the name, or None. Wildcards match through their base name."""

    name = _clean_zone(name)

    if name.startswith("*."):
        name = name[2:]

    best = None

    for entry in load_credentials() if entries is None else entries:
        zone = entry["zone"]

        if name != zone and not name.endswith("." + zone):
            continue

        if entry["provider"] in EXACT_ZONE_ONLY and name != zone:
            continue

        if best is None or len(zone) > len(best["zone"]):
            best = entry

    return best

"""
hd_DomainStore.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import copy
import json
import os
import re
import threading

from pymodules.hd_FunctionsGlobals import user_packages_domains_file

domains_file = user_packages_domains_file

PROTOCOLS = ("auto", "http", "https")

# Only gated exists until per-domain access lands
MODES = ("gated",)

LAN_SUFFIX = ".homedock.local"

_LABEL = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
_INVALID_SLUG_CHARS = re.compile(r"[^a-z0-9-]")
_REPEATED_DASHES = re.compile(r"-{2,}")

_lock = threading.RLock()

_cache = {"signature": None, "apps": {}}


class DomainError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def slugify_container_name(name):
    slug = name.strip().lower().replace("_", "-").replace(".", "-")
    slug = _INVALID_SLUG_CHARS.sub("", slug)
    slug = _REPEATED_DASHES.sub("-", slug).strip("-")

    return slug[:63]


def reserved_hosts():
    from pymodules.hd_AppSubdomains import get_desktop_hosts

    return get_desktop_hosts()


def reset_cache():
    with _lock:
        _cache["signature"] = None
        _cache["apps"] = {}


def _signature():
    try:
        stat = os.stat(domains_file)
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def _load():
    signature = _signature()

    if _cache["signature"] == signature and (signature is not None or _cache["apps"] == {}):
        return _cache["apps"]

    apps = {}

    if signature is not None:
        try:
            with open(domains_file, "r") as handle:
                stored = json.load(handle)

            if isinstance(stored, dict):
                apps = {str(name): app for name, app in stored.items() if isinstance(app, dict) and isinstance(app.get("domains"), list)}
        except (OSError, ValueError):
            apps = {}

    _cache["signature"] = signature
    _cache["apps"] = apps

    return apps


def _save(apps):
    try:
        os.makedirs(os.path.dirname(domains_file), exist_ok=True)

        temporary = domains_file + ".tmp"

        with open(temporary, "w") as handle:
            json.dump(apps, handle, indent=1, sort_keys=True)

        os.chmod(temporary, 0o600)
        os.replace(temporary, domains_file)
    except OSError as error:
        raise DomainError(f"Could not save the domain list: {error}", 500)

    _cache["signature"] = _signature()
    _cache["apps"] = apps


def validate_fqdn(raw):
    fqdn = (raw or "").strip().lower().rstrip(".")

    if not fqdn or len(fqdn) > 253:
        raise DomainError("Enter a domain name such as app.example.com.")

    if "*" in fqdn:
        raise DomainError("Wildcard names are not supported. Add each name on its own.")

    labels = fqdn.split(".")

    if len(labels) < 2:
        raise DomainError("A domain name needs at least two parts, such as app.example.com.")

    if not all(_LABEL.fullmatch(label) for label in labels):
        raise DomainError(f"{fqdn} is not a valid domain name.")

    if labels[-1].isdigit():
        raise DomainError("IP addresses cannot be used as domains. Use a name.")

    if fqdn.endswith(".localhost") or (fqdn.endswith(".local") and not fqdn.endswith(LAN_SUFFIX)):
        raise DomainError(f"Only names under {LAN_SUFFIX.lstrip('.')} are allowed for local use.")

    if fqdn in reserved_hosts():
        raise DomainError(f"{fqdn} is an address of HomeDock OS itself.")

    return fqdn


def _validate_port(port):
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise DomainError("Port must be a number between 1 and 65535.")

    return port


def _validate_protocol(protocol):
    if protocol not in PROTOCOLS:
        raise DomainError("Protocol must be auto, http or https.")

    return protocol


def _validate_path(path):
    path = (path or "").strip()

    if not path:
        return ""

    if not path.startswith("/") or re.search(r"[\s\\]", path) or ".." in path.split("/"):
        raise DomainError("Path must start with / and contain no spaces or '..'.")

    return path.rstrip("/")


def _validate_mode(mode):
    if mode not in MODES:
        raise DomainError("Access mode must be gated.")

    return mode


def _unique_slug(apps, container):
    base = slugify_container_name(container) or "app"
    taken = {app.get("slug") for name, app in apps.items() if name != container}
    slug, number = base, 2

    while slug in taken:
        suffix = f"-{number}"
        slug = base[: 63 - len(suffix)] + suffix
        number += 1

    return slug


def _ensure(apps, container):
    app = apps.get(container)

    if app is None:
        app = apps[container] = {"slug": _unique_slug(apps, container), "web_port": None, "domains": []}

    return app


def _owner_of(apps, fqdn):
    for name, app in apps.items():
        if any(domain["fqdn"] == fqdn for domain in app["domains"]):
            return name

    return None


def ensure_app(container):
    with _lock:
        apps = copy.deepcopy(_load())

        if container not in apps:
            _ensure(apps, container)
            _save(apps)

        return copy.deepcopy(apps[container])


def get_app(container):
    with _lock:
        app = _load().get(container)

        return copy.deepcopy(app) if app else None


def list_apps():
    with _lock:
        return copy.deepcopy(_load())


def add_domain(container, fqdn, port, protocol="auto", path="", mode="gated"):
    with _lock:
        fqdn = validate_fqdn(fqdn)
        entry = {"fqdn": fqdn, "port": _validate_port(port), "protocol": _validate_protocol(protocol), "path": _validate_path(path), "mode": _validate_mode(mode)}

        apps = copy.deepcopy(_load())
        owner = _owner_of(apps, fqdn)

        if owner is not None:
            raise DomainError(f"{fqdn} is already used by {owner}.", 409)

        _ensure(apps, container)["domains"].append(entry)
        _save(apps)

        return copy.deepcopy(entry)


def update_domain(container, fqdn, port=None, protocol=None, path=None, mode=None, primary=False):
    with _lock:
        fqdn = (fqdn or "").strip().lower().rstrip(".")
        apps = copy.deepcopy(_load())
        domains = apps.get(container, {}).get("domains", [])
        entry = next((d for d in domains if d["fqdn"] == fqdn), None)

        if entry is None:
            raise DomainError(f"{fqdn} is not a domain of {container}.", 404)

        if port is not None:
            entry["port"] = _validate_port(port)

        if protocol is not None:
            entry["protocol"] = _validate_protocol(protocol)

        if path is not None:
            entry["path"] = _validate_path(path)

        if mode is not None:
            entry["mode"] = _validate_mode(mode)

        if primary:
            domains.remove(entry)
            domains.insert(0, entry)

        _save(apps)

        return copy.deepcopy(entry)


def remove_domain(container, fqdn):
    with _lock:
        fqdn = (fqdn or "").strip().lower().rstrip(".")
        apps = copy.deepcopy(_load())
        domains = apps.get(container, {}).get("domains", [])
        remaining = [d for d in domains if d["fqdn"] != fqdn]

        if len(remaining) == len(domains):
            raise DomainError(f"{fqdn} is not a domain of {container}.", 404)

        apps[container]["domains"] = remaining
        _save(apps)


def set_web_port(container, port):
    with _lock:
        apps = copy.deepcopy(_load())
        _ensure(apps, container)["web_port"] = None if port is None else _validate_port(port)
        _save(apps)


def delete_app(container):
    with _lock:
        apps = copy.deepcopy(_load())

        if apps.pop(container, None) is not None:
            _save(apps)


def lookup_domain(host):
    host = (host or "").strip().lower().rstrip(".")

    with _lock:
        for container, app in _load().items():
            for domain in app["domains"]:
                if domain["fqdn"] == host:
                    return container, copy.deepcopy(domain)

    return None


def lookup_slug(slug):
    slug = (slug or "").strip().lower()

    with _lock:
        for container, app in _load().items():
            if app.get("slug") == slug:
                return container, copy.deepcopy(app)

    return None

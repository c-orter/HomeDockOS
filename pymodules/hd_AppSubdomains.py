"""
hd_AppSubdomains.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import os
import re

from pymodules.hd_FunctionsNetwork import local_ip, internet_ip
from pymodules.hd_FunctionsHostSelector import docker_host
from pymodules.hd_FunctionsConfig import read_config
from pymodules.hd_DomainStore import list_apps, lookup_domain, slugify_container_name  # noqa: F401  (slugify is re-exported)

_IPV4_HOST = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")

BASE_HOSTNAME = "homedock.local"

LOOPBACK_HOSTNAME = "homedock.localhost"


def get_slug_map():
    """{slug: {container, port, trail}} for every installed container that has a window port."""

    from pymodules.hd_BackendResolver import sync_installed_apps, web_port, compose_file_for
    from pymodules.hd_DockerAPIContainerData import load_suggested_trails

    sync_installed_apps()

    trails = load_suggested_trails()
    slugs = {}

    for container, app in list_apps().items():
        port = web_port(container)

        if port is None:
            continue

        stem = os.path.splitext(os.path.basename(compose_file_for(container) or ""))[0]

        slugs[app["slug"]] = {"container": container, "port": port, "trail": (trails.get(stem) or trails.get(container) or "").strip("/")}

    return slugs


def lookup_slug(slug):
    if not slug:
        return None

    return get_slug_map().get(slug.lower())


def get_desktop_hosts():
    # HDOS00043
    hosts = {"localhost", BASE_HOSTNAME, LOOPBACK_HOSTNAME, docker_host}

    for value in (local_ip, internet_ip):
        if value:
            hosts.add(value)

    try:
        base_domain = read_config().get("base_domain")
        if base_domain:
            hosts.add(base_domain.strip().lower())
    except Exception:
        pass

    return {host.lower() for host in hosts if host}


# HDOS00099
def get_emittable_hosts():
    hosts = get_desktop_hosts()

    if BASE_HOSTNAME not in hosts:
        return hosts

    try:
        from pymodules.hd_ThreadZeroConf import base_hostname_owned

        owned = base_hostname_owned()
    except Exception:
        owned = False

    if not owned:
        hosts.discard(BASE_HOSTNAME)

    return hosts


def split_host(host_header):
    """Return (slug, trail) for a Host header, stripping any port."""

    if not host_header:
        return "", ""

    host = host_header.strip().lower()

    # HDOS00021
    if host.startswith("["):
        return "", ""

    host = host.split(":")[0].rstrip(".")

    if "." not in host:
        return "", ""

    # HDOS00044
    if _IPV4_HOST.fullmatch(host):
        return "", ""

    slug, _, trail = host.partition(".")

    return slug, trail


def resolve_app_for_host(host_header):
    """The app a Host header addresses: an exact stored domain first, then the app's window address <slug>.<this host>."""

    if not host_header:
        return None

    bare_host = host_header.strip().lower().split(":")[0].rstrip(".")

    if bare_host in get_desktop_hosts():
        return None

    found = lookup_domain(bare_host)

    if found is not None:
        container, domain = found
        app = list_apps()[container]

        return {"slug": app["slug"], "container": container, "port": domain["port"], "trail": domain["path"].strip("/"), "protocol": domain["protocol"], "mode": domain.get("mode", "gated"), "host_trail": "", "fqdn": bare_host, "implicit": False}

    slug, host_trail = split_host(host_header)
    if not slug or not host_trail:
        return None

    # HDOS00104
    if host_trail.endswith(".local") or host_trail == "local":
        return None

    entry = lookup_slug(slug)

    if entry is None:
        return None

    # HDOS00034
    return {"slug": slug, "host_trail": host_trail, "protocol": "auto", "mode": "gated", "fqdn": bare_host, "implicit": True, **entry}


# HDOS00131
def is_app_namespace(host_header):

    if not host_header:
        return False

    host = host_header.strip().lower()

    if host.startswith("["):
        return False

    bare_host = host.split(":")[0].rstrip(".")
    desktop_hosts = get_desktop_hosts()

    if bare_host in desktop_hosts or _IPV4_HOST.fullmatch(bare_host):
        return False

    if bare_host.endswith(".local"):
        return False

    return any(bare_host.endswith(f".{desktop_host}") for desktop_host in desktop_hosts)


def build_forwarding_headers(public_host, scheme, client, forwarded_for=None):
    headers = {"host": public_host}

    if client:
        headers["x-forwarded-for"] = f"{forwarded_for}, {client[0]}" if forwarded_for else client[0]

    headers["x-forwarded-proto"] = scheme
    headers["x-forwarded-host"] = public_host
    headers["x-real-ip"] = client[0] if client else ""

    return headers

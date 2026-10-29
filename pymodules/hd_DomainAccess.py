"""
hd_DomainAccess.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

from pymodules.hd_DomainStore import LAN_SUFFIX
from pymodules.hd_FunctionsConfig import read_config
from pymodules.hd_FunctionsNativeSSL import get_cert_domains_and_type, ssl_enabled
from pymodules.hd_LocalHTTPAccess import is_local_only_name

LAN_DASHBOARD_HOST = LAN_SUFFIX.lstrip(".")


def cert_covers_name(fqdn, cert_domains):
    """True when one of the certificate names is the host itself or a wildcard one label above it."""

    host = (fqdn or "").strip().lower().rstrip(".")

    if not host:
        return False

    parent = host.partition(".")[2]

    for name in cert_domains:
        name = name.strip().lower()

        if name == host or (name.startswith("*.") and parent and name[2:] == parent):
            return True

    return False


def direct_refusal(fqdn):
    """Why a domain cannot be public, or None when it can: HTTPS with a certificate that covers the name."""

    if is_local_only_name(fqdn):
        return "Public access is not available for .local and .localhost names."

    if not ssl_enabled():
        return "Public access needs HTTPS, and HomeDock OS has no certificate yet."

    info = get_cert_domains_and_type()

    if info.get("is_self_signed"):
        return "Public access needs a trusted certificate, and the current one is self-signed."

    if not cert_covers_name(fqdn, info.get("domains", [])):
        return f"The current certificate does not cover {fqdn}."

    return None


def is_direct(app, scheme):
    """Whether a request to this app may skip the HomeDock OS login."""

    if app.get("implicit", True) or app.get("mode") != "direct" or scheme != "https":
        return False

    return direct_refusal(app["fqdn"]) is None


def dashboard_host_for(fqdn):
    """Where the HomeDock OS login for a domain lives, or None when there is nowhere to send the user."""

    if fqdn.endswith(LAN_SUFFIX):
        return LAN_DASHBOARD_HOST

    base_domain = (read_config().get("base_domain") or "").strip().lower().rstrip(".")

    return base_domain or None

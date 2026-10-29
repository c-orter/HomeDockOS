"""
hd_BaseDomain.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import re
from urllib.parse import urlparse

from publicsuffixlist import PublicSuffixList

_psl = PublicSuffixList()

_DOMAIN_REGEX = re.compile(r"^(?!-)([a-z0-9-]{1,63}(?<!-)\.)+[a-z][a-z0-9-]{0,62}$")


def validate_base_domain(raw):
    """Returns (domain, error). An empty value is allowed and means no base domain."""

    value = (raw or "").strip().lower()

    if not value:
        return "", None

    if "://" not in value:
        value = "http://" + value

    host = (urlparse(value).hostname or "").rstrip(".")

    if host.startswith("www."):
        host = host[4:]

    if not _DOMAIN_REGEX.match(host):
        return "", "Base domain must be a valid domain name such as home.example.com."

    if _psl.privatesuffix(host) is None:
        return "", f"{host} is a public suffix and cannot be a base domain. Use a domain you own, such as home.{host}."

    return host, None

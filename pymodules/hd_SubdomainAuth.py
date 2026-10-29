"""
hd_SubdomainAuth.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

from urllib.parse import quote, urlsplit

from flask import jsonify, redirect, request, session, url_for
from flask_login import current_user, login_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from pymodules.hd_HDOSWebServerInit import homedock_www
from pymodules.hd_AppSubdomains import lookup_slug, slugify_container_name
from pymodules.hd_DomainStore import lookup_domain
from pymodules.hd_FunctionsConfig import read_config
from pymodules.hd_FunctionsNativeSSL import ssl_enabled, get_cert_domains_and_type, cert_covers_subdomains_of

TOKEN_QUERY_PARAM = "__hd_token"
TOKEN_COOKIE_NAME = "homedock_app_auth"

# HDOS00022
HANDOFF_MAX_AGE = 60
SESSION_MAX_AGE = 24 * 60 * 60

_SALT = "homedock-app-subdomain"


def _serializer():

    secret = homedock_www.config.get("SECRET_KEY")

    if not secret:
        return None

    return URLSafeTimedSerializer(secret, salt=_SALT)


def mint_app_token(container, fqdn):
    serializer = _serializer()

    if serializer is None:
        return None

    return serializer.dumps({"container": container, "fqdn": fqdn})


def verify_app_token(token, container, fqdn, max_age):
    """A token only opens the exact container and host it was minted for."""

    if not token or not container or not fqdn:
        return False

    serializer = _serializer()

    if serializer is None:
        return False

    try:
        payload = serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired, Exception):
        return False

    if not isinstance(payload, dict):
        return False

    return payload.get("container") == container and payload.get("fqdn") == fqdn


# HDOS00062
@login_required
def api_subdomain_diagnostics():
    """Why an app subdomain refused to load, which the browser probe cannot tell apart.

    A no-cors fetch rejects the same way for a name that does not resolve and for a
    certificate the browser will not accept, so the window used to blame missing
    wildcard DNS for both. The certificate is something we can answer for.
    """

    host = request.host.split(":")[0].strip().lower().rstrip(".")

    # HDOS00076
    if not request.is_secure or not ssl_enabled():
        return jsonify({"ssl": False, "covers_apps": False, "self_signed": False, "host": host, "alternative": None}), 200

    info = get_cert_domains_and_type()

    return (
        jsonify(
            {
                "ssl": True,
                "covers_apps": cert_covers_subdomains_of(host),
                "self_signed": bool(info.get("is_self_signed")),
                "host": host,
                "alternative": _covered_alternative(info.get("domains", []), host),
            }
        ),
        200,
    )


def _covered_alternative(domains, host):

    configured = (read_config().get("base_domain") or "").strip().lower().rstrip(".")

    covered = {domain[2:].strip().lower() for domain in domains if domain.startswith("*.")} - {host}

    return configured if configured in covered else None


@login_required
def api_app_token():
    """A handoff token for the app's window address, <slug>.<the host the dashboard is on>."""

    data = request.get_json(silent=True) or {}

    requested = data.get("slug") or data.get("container")
    if not isinstance(requested, str):
        return jsonify({"error": "Missing app identifier."}), 400

    slug = slugify_container_name(requested)
    entry = lookup_slug(slug) if slug else None

    if entry is None:
        return jsonify({"error": "Unknown application."}), 404

    host = request.host.split(":")[0].strip().lower().rstrip(".")
    token = mint_app_token(entry["container"], f"{slug}.{host}")

    if token is None:
        return jsonify({"error": "Server not ready to issue app tokens."}), 503

    return jsonify({"slug": slug, "token": token, "param": TOKEN_QUERY_PARAM, "expires_in": HANDOFF_MAX_AGE})


_MAX_RETURN_LENGTH = 2048


def parse_return_target(raw):
    """(container, fqdn, url) for a return address, or None unless its host is a stored domain.

    The address is rebuilt from parsed parts so nothing else the caller sent can steer the redirect.
    """

    if not isinstance(raw, str) or not raw or len(raw) > _MAX_RETURN_LENGTH or any(ord(char) < 32 for char in raw):
        return None

    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        return None

    if parts.scheme not in ("http", "https") or parts.username is not None or parts.password is not None or not parts.hostname:
        return None

    path = parts.path or "/"

    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        return None

    fqdn = parts.hostname.lower().rstrip(".")
    found = lookup_domain(fqdn)

    if found is None:
        return None

    url = f"{parts.scheme}://{fqdn}" + (f":{port}" if port else "") + path + (f"?{parts.query}" if parts.query else "")

    return found[0], fqdn, url


def app_auth():
    """The dashboard end of the gated flow: sign in, then send the browser back with a token for that one domain."""

    target = parse_return_target(request.args.get("return"))

    if target is None:
        return "This address is not an application of this HomeDock OS.", 400

    if not current_user.is_authenticated:
        session["post_login_return"] = request.full_path.rstrip("?")
        return redirect(url_for("login_page"))

    container, fqdn, url = target
    token = mint_app_token(container, fqdn)

    if token is None:
        return "Server not ready to issue app tokens.", 503

    parts = urlsplit(url)
    query = f"{parts.query}&" if parts.query else ""
    location = f"{parts.scheme}://{parts.netloc}{parts.path}?{query}{TOKEN_QUERY_PARAM}={quote(token)}"

    response = redirect(location)
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"

    return response

"""
hd_UIDomains.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

from flask import jsonify, request
from flask_login import login_required

from pymodules.hd_BackendResolver import container_ports, installed_containers, reachability, sync_installed_apps, web_port
from pymodules.hd_DomainAccess import direct_refusal
from pymodules.hd_CertManager import name_statuses, days_until_expiry
from pymodules.hd_CertPlan import resolves_to_server
from pymodules.hd_FunctionsConfig import read_config
from pymodules.hd_DomainStore import DomainError, add_domain, get_app, list_apps, remove_domain, set_web_port, suggest_slug, update_domain


def _error(error):
    return jsonify({"status": "bad_request" if error.status == 400 else "error", "message": error.message}), error.status


def _app_json(container, app):
    reachable, reason = reachability(container)

    certificate = {item["name"]: item for item in name_statuses([domain["fqdn"] for domain in app["domains"]])}

    domains = [{**domain, "direct_refusal": direct_refusal(domain["fqdn"]), "certificate": certificate.get(domain["fqdn"], {"status": "pending", "reason": ""})} for domain in app["domains"]]

    base = (read_config().get("base_domain") or "").strip().lower().rstrip(".")
    effective = web_port(container)
    ports = sorted({*container_ports(container), *([effective] if effective else []), *(domain["port"] for domain in app["domains"])})

    return {
        "container": container,
        "slug": app["slug"],
        "web_port": app["web_port"],
        "effective_web_port": effective,
        "ports": ports,
        "base_domain": base,
        "suggestion": f"{app['slug']}.{base}" if base else "",
        "certificate_expires_in_days": days_until_expiry(),
        "reachable": reachable,
        "unreachable_reason": reason,
        "domains": domains,
    }


def _check_direct(fqdn, mode):
    if mode == "direct":
        reason = direct_refusal(str(fqdn or "").strip().lower().rstrip("."))

        if reason:
            raise DomainError(reason)


def _known_container(container):
    if not container or (container not in installed_containers() and get_app(container) is None):
        raise DomainError("Unknown application.", 404)

    return container


def _body():
    return request.get_json(silent=True) or {}


@login_required
def api_domains():
    sync_installed_apps()

    container = request.args.get("container")

    if container:
        app = get_app(container)

        if app is None:
            return jsonify({"status": "error", "message": "Unknown application."}), 404

        return jsonify(_app_json(container, app)), 200

    return jsonify({"apps": [_app_json(name, app) for name, app in sorted(list_apps().items())]}), 200


@login_required
def api_domains_add():
    data = _body()

    try:
        container = _known_container(str(data.get("container", "")))
        mode = data.get("mode", "gated")
        _check_direct(data.get("fqdn"), mode)
        domain = add_domain(container, data.get("fqdn"), data.get("port"), data.get("protocol", "auto"), data.get("path", ""), mode)
    except DomainError as error:
        return _error(error)

    return jsonify({"status": "saved", "domain": domain}), 200


@login_required
def api_domains_update():
    data = _body()

    try:
        container = _known_container(str(data.get("container", "")))
        mode = data.get("mode")
        _check_direct(data.get("fqdn"), mode)
        domain = update_domain(container, data.get("fqdn"), port=data.get("port"), protocol=data.get("protocol"), path=data.get("path"), mode=mode, primary=bool(data.get("primary")))
    except DomainError as error:
        return _error(error)

    return jsonify({"status": "saved", "domain": domain}), 200


@login_required
def api_domains_remove():
    data = _body()

    try:
        container = _known_container(str(data.get("container", "")))
        remove_domain(container, data.get("fqdn"))
    except DomainError as error:
        return _error(error)

    return jsonify({"status": "removed"}), 200


@login_required
def api_domains_web_port():
    data = _body()

    try:
        container = _known_container(str(data.get("container", "")))
        set_web_port(container, data.get("port"))
    except DomainError as error:
        return _error(error)

    return jsonify({"status": "saved", "web_port": web_port(container)}), 200


@login_required
def api_domains_check():
    """Whether a name's DNS points at this server, so the manager can say so before anyone relies on it."""

    fqdn = str(_body().get("fqdn", "")).strip().lower().rstrip(".")

    if not fqdn:
        return jsonify({"status": "bad_request", "message": "A domain name is required."}), 400

    ok, reason = resolves_to_server(fqdn)

    return jsonify({"fqdn": fqdn, "resolves": ok, "reason": reason}), 200


@login_required
def api_domains_suggestion():
    """The name the install form offers before the app exists: its slug under the base domain, empty when there is no base domain."""

    container = str(request.args.get("container", "")).strip()

    if not container:
        return jsonify({"status": "bad_request", "message": "An application name is required."}), 400

    base = (read_config().get("base_domain") or "").strip().lower().rstrip(".")

    return jsonify({"base_domain": base, "suggestion": f"{suggest_slug(container)}.{base}" if base else ""}), 200

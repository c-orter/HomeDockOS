"""
hd_UIDomains.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

from flask import jsonify, request
from flask_login import login_required

from pymodules.hd_BackendResolver import installed_containers, reachability, sync_installed_apps, web_port
from pymodules.hd_DomainStore import DomainError, add_domain, get_app, list_apps, remove_domain, set_web_port, update_domain


def _error(error):
    return jsonify({"status": "bad_request" if error.status == 400 else "error", "message": error.message}), error.status


def _app_json(container, app):
    reachable, reason = reachability(container)

    return {"container": container, "slug": app["slug"], "web_port": app["web_port"], "effective_web_port": web_port(container), "reachable": reachable, "unreachable_reason": reason, "domains": app["domains"]}


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
        domain = add_domain(container, data.get("fqdn"), data.get("port"), data.get("protocol", "auto"), data.get("path", ""))
    except DomainError as error:
        return _error(error)

    return jsonify({"status": "saved", "domain": domain}), 200


@login_required
def api_domains_update():
    data = _body()

    try:
        container = _known_container(str(data.get("container", "")))
        domain = update_domain(container, data.get("fqdn"), port=data.get("port"), protocol=data.get("protocol"), path=data.get("path"), primary=bool(data.get("primary")))
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

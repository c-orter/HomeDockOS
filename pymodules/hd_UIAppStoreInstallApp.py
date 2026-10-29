"""
hd_UIAppStoreInstallApp.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

from flask import jsonify, request
from flask_login import login_required, current_user

from pymodules.hd_InstallPipeline import InstallError, enqueue_install, installation_status


@login_required
def app_store_install_container():
    data = request.get_json(silent=True) if request.is_json else request.form
    data = data or {}
    container_name = data.get("containerName")

    if not container_name:
        return jsonify({"success": False, "message": "Missing container name"}), 400

    try:
        enqueue_install(current_user.id.lower(), container_name, data.get("contentHash"))
    except InstallError as e:
        return jsonify(e.payload()), e.status

    return jsonify(success=True, message="Installation for {} has been queued.".format(container_name))


@login_required
def get_installation_status():
    return jsonify(**installation_status())

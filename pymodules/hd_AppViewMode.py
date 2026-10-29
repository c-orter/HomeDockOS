"""
hd_AppViewMode.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import os
import re
import json
import threading

from flask import jsonify, request
from flask_login import login_required, current_user

from pymodules.hd_FunctionsGlobals import user_packages_app_open_folder
from pymodules.hd_AppSubdomains import slugify_container_name

# HDOS00077
MODES = ("window", "tab")

DEFAULT_MODE = "window"

_lock = threading.Lock()


def _store_path(username):
    safe = re.sub(r"[^a-zA-Z0-9]", "", (username or "")).lower()[:64]

    if not safe:
        return None

    return os.path.join(user_packages_app_open_folder, f"{safe}.json")


def _read_all(username):
    path = _store_path(username)

    if not path:
        return {}

    try:
        with open(path, "r") as handle:
            stored = json.load(handle)
    except (FileNotFoundError, IOError, OSError, ValueError):
        return {}

    if not isinstance(stored, dict):
        return {}

    return {str(container): value for container, value in stored.items() if value in MODES}


def _write_all(username, entries):
    path = _store_path(username)

    if not path:
        return False

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w") as handle:
            json.dump(entries, handle, indent=1, sort_keys=True)
    except OSError:
        return False

    return True


def get_view_modes(username):
    with _lock:
        return _read_all(username)


def set_view_mode(username, container, mode):
    container = (container or "").strip()
    mode = (mode or "").strip().lower()

    if not container or mode not in MODES:
        return False

    with _lock:
        entries = _read_all(username)
        entries[container] = mode

        return _write_all(username, entries)


@login_required
def api_app_view_mode():
    username = current_user.id

    if request.method == "GET":
        return jsonify({"modes": get_view_modes(username), "default": DEFAULT_MODE}), 200

    data = request.get_json(silent=True) or {}

    container = str(data.get("container", ""))

    if not container or not slugify_container_name(container):
        return jsonify({"status": "bad_request", "message": "Unknown application."}), 400

    mode = str(data.get("mode", ""))

    if not set_view_mode(username, container, mode):
        return jsonify({"status": "bad_request", "message": "Unknown view mode."}), 400

    return jsonify({"status": "saved", "container": container, "mode": mode}), 200

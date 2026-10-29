"""
hd_UIAppStoreReadSaveYML.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import os
import re
import json
import yaml

from flask_login import login_required, current_user
from flask import jsonify, request

from pymodules.hd_FunctionsGlobals import current_directory
from pymodules.hd_FunctionsNativeSSL import ssl_enabled
from pymodules.hd_ComposeDevHooks import process_devhooks, extract_devhook_placeholders, DEVHOOK_USER_NAME_KEY, DEVHOOK_PASSWORD_KEY, DEVHOOK_SYSTEM_PASSWORD_KEY, DEVHOOK_RANDOM_STRING_KEY
from pymodules.hd_HDSPackageManager import normalize_app_slug
from pymodules.hd_InstallPipeline import InstallError, stage_config
from pymodules.hd_ImageDownloadSize import compose_images, host_architecture, images_download_size


@login_required
def get_appstore_info():
    containerName = request.args.get("containerName")

    if not is_valid_container_name(containerName):
        return jsonify({"success": False, "message": "Invalid container name"}), 400

    path_to_yml_files = os.path.join(current_directory, "app-store")

    use_ssl = ssl_enabled()

    if use_ssl and os.path.exists(os.path.join(path_to_yml_files, "ssl", f"{containerName}.yml")):
        yml_file_path = os.path.join(path_to_yml_files, "ssl", f"{containerName}.yml")
        use_ssl = True

    elif os.path.exists(os.path.join(path_to_yml_files, f"{containerName}.yml")):
        yml_file_path = os.path.join(path_to_yml_files, f"{containerName}.yml")
        use_ssl = False

    elif os.path.exists(os.path.join(current_directory, "_user_packages", "_available", f"{containerName}.yml")):
        yml_file_path = os.path.join(current_directory, "_user_packages", "_available", f"{containerName}.yml")
        use_ssl = False

    elif " " in containerName:
        normalized_name = normalize_app_slug(containerName)
        if os.path.exists(os.path.join(current_directory, "_user_packages", "_available", f"{normalized_name}.yml")):
            yml_file_path = os.path.join(current_directory, "_user_packages", "_available", f"{normalized_name}.yml")
            use_ssl = False
        else:
            return jsonify({"success": False, "message": "Container not found"}), 404
    else:
        return jsonify({"success": False, "message": "Container not found"}), 404

    with open(yml_file_path, "r") as file:
        yml_str = file.read()

        placeholders = extract_devhook_placeholders(yml_str)
        user_placeholder_present = placeholders[DEVHOOK_USER_NAME_KEY]
        password_placeholder_present = placeholders[DEVHOOK_PASSWORD_KEY]
        sys_password_placeholder_present = placeholders[DEVHOOK_SYSTEM_PASSWORD_KEY]
        random_string_placeholder_present = placeholders[DEVHOOK_RANDOM_STRING_KEY]

        yml_str, devhook_values = process_devhooks(yml_str)

        try:
            yml_data = yaml.safe_load(yml_str)
        except yaml.YAMLError as e:
            print(f"Error parsing YAML: {str(e)}")
            return jsonify({"success": False, "message": "Invalid YML"}), 500

        is_group = any("HDGroup" in service_data.get("labels", {}) for service_data in yml_data.get("services", {}).values())

        main_service_name = None
        main_service_data = None
        hd_group = None
        hd_role = None

        dependencies = []
        if is_group:
            for service_name, service_data in yml_data.get("services", {}).items():
                if service_data.get("labels", {}).get("HDRole") == "main":
                    main_service_name = service_name
                    main_service_data = service_data
                    hd_group = service_data.get("labels", {}).get("HDGroup")
                    hd_role = service_data.get("labels", {}).get("HDRole")
                    break

            for service_name, service_data in yml_data.get("services", {}).items():
                if service_data.get("labels", {}).get("HDRole") == "dependency":
                    dependencies.append(service_name)

            if main_service_name is None or main_service_data is None:
                return jsonify({"success": False, "message": "Main container not found in group"}), 404
        else:
            main_service_name, main_service_data = next(iter(yml_data.get("services", {}).items()), (None, None))

        if main_service_name is None or main_service_data is None:
            return jsonify({"success": False, "message": "No service data found"}), 404

        ports = main_service_data.get("ports", [])
        volumes = main_service_data.get("volumes", [])

        environment_raw = main_service_data.get("environment", {})
        environment = {}
        if isinstance(environment_raw, dict):
            for key, value in environment_raw.items():
                value_str = str(value)
                if value_str not in ["[[HD_USER_NAME]]", "[[HD_PASSWORD]]", "[[HD_SYSTEM_PASSWORD]]", "[[HD_RND_STR]]"] and not (user_placeholder_present and value_str == devhook_values.get("user_name")) and not (password_placeholder_present and value_str == devhook_values.get("password")) and not (sys_password_placeholder_present and value_str == devhook_values.get("sys_password")) and not (random_string_placeholder_present and value_str == devhook_values.get("random_string")):
                    environment[key] = value
        elif isinstance(environment_raw, list):
            for env_item in environment_raw:
                if "=" in env_item:
                    key, value = env_item.split("=", 1)
                    if value not in ["[[HD_USER_NAME]]", "[[HD_PASSWORD]]", "[[HD_SYSTEM_PASSWORD]]", "[[HD_RND_STR]]"] and not (user_placeholder_present and value == devhook_values.get("user_name")) and not (password_placeholder_present and value == devhook_values.get("password")) and not (sys_password_placeholder_present and value == devhook_values.get("sys_password")) and not (random_string_placeholder_present and value == devhook_values.get("random_string")):
                        environment[key] = value

        networks = []
        network_mode = main_service_data.get("network_mode")
        if network_mode:
            networks = [network_mode]
        else:
            networks_dict = main_service_data.get("networks", {})
            networks = list(networks_dict.keys()) if isinstance(networks_dict, dict) else (networks_dict if isinstance(networks_dict, list) else [])

        cap_add = main_service_data.get("cap_add", [])
        privileged = main_service_data.get("privileged", False)

        yml_data_copy = yml_data.copy()
        yml_str = yaml.dump(yml_data_copy)

        yml_str, _ = process_devhooks(yml_str)

        return jsonify({"success": True, "data": {"ports": ports, "volumes": volumes, "environment": environment, "networks": networks, "capabilities": cap_add, "privileged": privileged, "ymlContent": yml_str, "dependencies": dependencies, "hd_group": hd_group, "hd_role": hd_role, "user_name": devhook_values["user_name"] if user_placeholder_present else None, "password": devhook_values["password"] if password_placeholder_present else None, "random_string": devhook_values["random_string"] if random_string_placeholder_present else None, "ssl_enabled": use_ssl}})


@login_required
def process_config():
    request_data = request.get_json(silent=True)
    if not request_data:
        return jsonify({"success": False, "message": "Invalid JSON payload"}), 400

    container_name = request_data.get("containerName")
    if not is_valid_container_name(container_name):
        return jsonify({"success": False, "message": "Invalid container name"}), 400

    try:
        content_hash = stage_config(current_user.id.lower(), container_name, request_data.get("configType"), request_data)
    except InstallError as e:
        return jsonify(e.payload()), e.status

    message = "YML updated successfully" if request_data.get("configType") == "advanced" else "YML updated successfully with simple configuration"

    return jsonify({"success": True, "message": message, "contentHash": content_hash})


_catalog_sizes = {"mtime": None, "sizes": {}}


def catalog_download_sizes():
    catalog_path = os.path.join(current_directory, "homedock-ui", "vue3", "static", "js", "__Data__", "AppStoreDefault.json")
    try:
        mtime = os.path.getmtime(catalog_path)
    except OSError:
        return {}

    if _catalog_sizes["mtime"] != mtime:
        try:
            with open(catalog_path, "r", encoding="utf-8") as file:
                catalog = json.load(file)
            _catalog_sizes["sizes"] = {app["name"]: app["download_size"] for app in catalog if isinstance(app.get("download_size"), dict)}
        except (OSError, ValueError, KeyError, TypeError):
            _catalog_sizes["sizes"] = {}
        _catalog_sizes["mtime"] = mtime

    return _catalog_sizes["sizes"]


def resolve_appstore_yml_path(container_name):
    app_store_folder = os.path.join(current_directory, "app-store")
    user_packages_folder = os.path.join(current_directory, "_user_packages", "_available")

    candidates = [os.path.join(app_store_folder, f"{container_name}.yml"), os.path.join(user_packages_folder, f"{container_name}.yml")]
    if " " in container_name:
        candidates.append(os.path.join(user_packages_folder, f"{normalize_app_slug(container_name)}.yml"))

    return next((path for path in candidates if os.path.exists(path)), None)


@login_required
def get_app_download_size():
    containerName = request.args.get("containerName")

    if not is_valid_container_name(containerName):
        return jsonify({"success": False, "message": "Invalid container name"}), 400

    architecture = host_architecture()

    catalog_size = catalog_download_sizes().get(containerName, {}).get(architecture)
    if isinstance(catalog_size, int):
        return jsonify({"success": True, "data": {"size": catalog_size, "complete": True, "compatible": True, "architecture": architecture}})

    yml_file_path = resolve_appstore_yml_path(containerName)
    if not yml_file_path:
        return jsonify({"success": False, "message": "Container not found"}), 404

    with open(yml_file_path, "r") as file:
        result = images_download_size(compose_images(file.read()), architecture)

    if result is None:
        return jsonify({"success": True, "data": None})

    return jsonify({"success": True, "data": {**result, "architecture": architecture}})


def is_valid_container_name(name):
    if not name or not isinstance(name, str):
        return False
    return re.match(r"^[a-zA-Z0-9-_ ]+\Z", name) is not None

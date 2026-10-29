"""
hd_DockerAPIContainerData.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import os
import re
import json


from flask import jsonify, request
from flask_login import login_required, current_user

from pymodules.hd_FunctionsGlobals import compose_upload_folder, current_directory, user_packages_available_folder
from pymodules.hd_FunctionsSanitize import sanitize_container_name
from pymodules.hd_AppSubdomains import slugify_container_name
from pymodules.hd_BackendResolver import web_port
from pymodules.hd_DomainStore import get_app
from pymodules.hd_ThreadContainerResourceUsage import cpu_usage, memory_usage, memory_bytes, memory_limit_bytes, network_rx_bytes, network_tx_bytes

from pymodules.hd_ClassDockerClientManager import DockerClientManager
from pymodules.hd_ThreadAppUpdatesChecker import get_updates_state
from pymodules.hd_AppUpdateMarks import get_unseen_updates

_appstore_json_path = os.path.join(current_directory, "homedock-ui", "vue3", "static", "js", "__Data__", "AppStoreDefault.json")

_app_store_cache = None
_app_store_external_cache = None
_suggested_ports_cache = None
_suggested_trails_cache = None


def invalidate_external_apps_cache():
    global _app_store_external_cache, _suggested_ports_cache, _suggested_trails_cache
    _app_store_external_cache = None
    _suggested_ports_cache = None
    _suggested_trails_cache = None


def _port_suffix():
    _, separator, host_port = request.host.rpartition(":")

    return f":{host_port}" if separator and host_port.isdigit() and not request.host.startswith("[") else ""


def primary_domain_url(domains, scheme, port_suffix):
    """Where "open in a tab" goes: the app's first domain, or None when it has none."""

    if not domains:
        return None

    return f"{scheme}://{domains[0]['fqdn']}{port_suffix}{domains[0]['path']}"


def load_suggested_ports():
    global _suggested_ports_cache

    if _suggested_ports_cache is None:
        try:
            with open(_appstore_json_path, "r", encoding="utf-8") as f:
                _suggested_ports_cache = {app["name"]: app["suggested_port"] for app in json.load(f) if "suggested_port" in app}
        except Exception as e:
            print(f"Warning: Could not load suggested ports: {e}")
            _suggested_ports_cache = {}

        try:
            if os.path.exists(user_packages_available_folder):
                for filename in os.listdir(user_packages_available_folder):
                    if filename.endswith(".yml.metadata"):
                        metadata_path = os.path.join(user_packages_available_folder, filename)
                        with open(metadata_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        if "suggested_port" in meta and meta.get("name"):
                            _suggested_ports_cache[meta["name"]] = meta["suggested_port"]
        except Exception:
            pass

    return _suggested_ports_cache


def load_suggested_trails():
    global _suggested_trails_cache

    if _suggested_trails_cache is None:
        try:
            with open(_appstore_json_path, "r", encoding="utf-8") as f:
                _suggested_trails_cache = {app["name"]: app["suggested_trail"] for app in json.load(f) if "suggested_trail" in app}
        except Exception as e:
            print(f"Warning: Could not load suggested trails: {e}")
            _suggested_trails_cache = {}

        try:
            if os.path.exists(user_packages_available_folder):
                for filename in os.listdir(user_packages_available_folder):
                    if filename.endswith(".yml.metadata"):
                        metadata_path = os.path.join(user_packages_available_folder, filename)
                        with open(metadata_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        if "suggested_trail" in meta and meta.get("name"):
                            _suggested_trails_cache[meta["name"]] = meta["suggested_trail"]
        except Exception:
            pass

    return _suggested_trails_cache


def load_app_store_data():
    global _app_store_cache, _app_store_external_cache

    if _app_store_cache is None:
        try:
            with open(_appstore_json_path, "r", encoding="utf-8") as f:
                _app_store_cache = {app["name"]: app.get("display_name", app["name"]) for app in json.load(f)}
        except Exception as e:
            print(f"Warning: Could not load AppStoreDefault.json: {e}")
            _app_store_cache = {}

    if _app_store_external_cache is None:
        _app_store_external_cache = {}
        try:
            if os.path.exists(user_packages_available_folder):
                for filename in os.listdir(user_packages_available_folder):
                    if filename.endswith(".yml.metadata"):
                        app_slug = filename.replace(".yml.metadata", "")
                        metadata_path = os.path.join(user_packages_available_folder, filename)
                        try:
                            with open(metadata_path, "r", encoding="utf-8") as f:
                                metadata = json.load(f)
                                display_name = metadata.get("display_name", metadata.get("name", app_slug))
                                icon_filename = metadata.get("icon_filename", f"{app_slug}.jpg")
                                _app_store_external_cache[app_slug] = {"display_name": display_name, "picture_path": f"user-images/{icon_filename}"}
                        except:
                            pass
        except Exception as e:
            print(f"Warning: Could not load external apps metadata: {e}")

    return _app_store_cache, _app_store_external_cache


def get_display_name_for_container(container_name: str) -> str:
    app_store, external_apps = load_app_store_data()

    sanitized = sanitize_container_name(container_name)

    if sanitized == "homedock-os":
        return "HomeDock OS"

    if sanitized in app_store:
        return app_store[sanitized]
    if sanitized in external_apps:
        if isinstance(external_apps[sanitized], dict):
            return external_apps[sanitized]["display_name"]
        return external_apps[sanitized]

    if "_" in sanitized:
        base_name = sanitized.split("_")[0]
        if base_name in app_store:
            return app_store[base_name]
        if base_name in external_apps:
            if isinstance(external_apps[base_name], dict):
                return external_apps[base_name]["display_name"]
            return external_apps[base_name]

    return sanitized


@login_required
def get_docker_containers():

    manager = DockerClientManager.get_instance()
    client = manager.get_client()

    containers = client.containers.list(all=True)
    container_data = []

    updates_dict = get_updates_state()
    unseen_updates = get_unseen_updates(current_user.id)

    port_suffix = _port_suffix()
    scheme = "https" if request.is_secure else "http"

    for container in containers:
        try:
            labels = container.labels

            if labels.get("HDDockerInDocker") == "true":
                continue

            compose_file_path = os.path.join(compose_upload_folder, f"{sanitize_container_name(container.name)}.yml")
            file_status = "exists" if os.path.exists(compose_file_path) else "not_exists"

            status_color_map = {"running": "success", "exited": "warning", "paused": "primary", "restarting": "dark", "dead": "dark", "removing": "danger", "created": "info"}
            statusColor = status_color_map.get(container.status, "default_color")

            sanitized_name = sanitize_container_name(container.name)
            image_path = "docker-icons/notfound.jpg"  # Default

            icon_candidates = [sanitized_name]
            if "_" in sanitized_name:
                icon_candidates.append(sanitized_name.split("_")[0])
            if labels.get("HDGroup"):
                icon_candidates.append(sanitize_container_name(labels["HDGroup"]))

            for candidate in icon_candidates:
                for ext in [".jpg", ".jpeg", ".png"]:
                    os_image_path = os.path.join(current_directory, "homedock-ui", "static", "images", f"docker-icons/{candidate}{ext}")
                    if os.path.exists(os_image_path):
                        image_path = f"docker-icons/{candidate}{ext}"
                        break
                if image_path != "docker-icons/notfound.jpg":
                    break

            if image_path == "docker-icons/notfound.jpg":
                app_store, external_apps = load_app_store_data()

                for candidate in icon_candidates:
                    if candidate in external_apps and isinstance(external_apps[candidate], dict):
                        image_path = external_apps[candidate]["picture_path"]
                        break

            host_display = request.host.split(":")[0]
            if host_display.startswith("www."):
                host_display = host_display[4:]

            # Published host ports are informational only: apps open through their domains or their window address
            ports_list = []
            for port, bindings in (container.attrs["NetworkSettings"]["Ports"] or {}).items():
                for item in bindings or []:
                    host_port = sanitize_port(item["HostPort"])
                    if host_port and host_port not in ports_list:
                        ports_list.append(host_port)

            stored = get_app(container.name) or {"domains": []}
            service_url = primary_domain_url(stored["domains"], scheme, port_suffix)
            openable = web_port(container.name) is not None

            display_name = get_display_name_for_container(container.name)

            started_at = container.attrs.get("State", {}).get("StartedAt", "") if container.status == "running" else ""

            basic_data = {
                "name": container.name,
                "slug": slugify_container_name(container.name),
                "display_name": display_name,
                "id": container.short_id,
                "status": container.status,
                "image": str(container.image.tags[0]) if container.image.tags else "",
                "image_path": image_path,
                "usagePercent": cpu_usage.get(container.name, 0),
                "memoryUsagePercent": memory_usage.get(container.name, 0),
                "memoryUsageBytes": memory_bytes.get(container.name, 0),
                "memoryLimitBytes": memory_limit_bytes.get(container.name, 0),
                "networkRxBytes": network_rx_bytes.get(container.name, 0),
                "networkTxBytes": network_tx_bytes.get(container.name, 0),
                "statusColor": statusColor,
                "host": host_display,
                "composeLink": file_status,
                "ports": ports_list,
                "service_url": service_url,
                "openable": openable,
                "domains": [domain["fqdn"] for domain in stored["domains"]],
                "startedAt": started_at,
                "has_update": updates_dict.get(container.name, False),
                "recently_updated": unseen_updates.get(container.name) == container.id,
            }

            if "HDGroup" in labels:
                basic_data["HDGroup"] = labels["HDGroup"]
            if "HDRole" in labels:
                basic_data["HDRole"] = labels["HDRole"]

            container_data.append(basic_data)

        except Exception as e:
            print(f"Warning: Could not process container {container.name}: {e}")
            continue

    return jsonify(container_data)


# HDOS00017
def is_valid_hostname(hostname):
    pattern = r"^[a-zA-Z0-9.-]*$"
    return re.match(pattern, hostname) is not None


def sanitize_port(port):
    pattern = r"^(\d{1,5})(/[a-zA-Z0-9/_-]*)?$"
    match = re.match(pattern, port)

    if match:
        port_number = int(match.group(1))
        if 0 <= port_number <= 65535:
            return port
    return None

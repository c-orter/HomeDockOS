"""
hd_InstalledConfig.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import os
import re
import yaml

from flask import jsonify, request
from flask_login import login_required

from pymodules.hd_FunctionsGlobals import compose_upload_folder
from pymodules.hd_ComposeDevHooks import process_devhooks, get_config_path, get_internal_storage_path
from pymodules.hd_ComposeWarnings import compose_warnings
from pymodules.hd_PortValidator import validate_ports

SECTIONS = ("ports", "volumes", "environment", "networks", "capabilities", "privileged", "restartPolicy")
NETWORK_MODES = ("host", "bridge", "none")
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*\Z")
SECRET_NAME = re.compile(r"pass|secret|token|key|pwd", re.IGNORECASE)
CONTAINER_NAME = re.compile(r"^[a-zA-Z0-9\-_ ]+\Z")
MASK = "••••••"


class InstalledConfigError(Exception):
    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra

    def payload(self):
        return {"success": False, "message": self.message, **self.extra}


# --- reading ---


def installed_compose_path(container_name) -> str:
    if not isinstance(container_name, str) or not CONTAINER_NAME.match(container_name):
        raise InstalledConfigError("Invalid container name")

    path = os.path.join(compose_upload_folder, f"{container_name}.yml")

    if not os.path.exists(path):
        raise InstalledConfigError("Container not found", 404)

    return path


def pick_main(yml_data):
    """The service the form edits: the group's HDRole=main service, else the first one."""

    services = (yml_data or {}).get("services") or {}

    for name, service in services.items():
        if isinstance(service, dict) and (service.get("labels") or {}).get("HDRole") == "main":
            return name, service

    return next(((name, service) for name, service in services.items() if isinstance(service, dict)), (None, None))


def _has_merge_keys(text: str) -> bool:
    return re.search(r"^\s*<<\s*:|[:\-]\s+[&*][A-Za-z0-9_-]+", text, re.MULTILINE) is not None


def _env_pairs(raw):
    """Env as an ordered {name: value-string} dict, or None when the shape cannot be shown as plain pairs."""

    if isinstance(raw, dict):
        if any(value is None or isinstance(value, (dict, list)) for value in raw.values()):
            return None
        return {str(key): str(value) for key, value in raw.items()}

    if isinstance(raw, list):
        pairs = {}
        for item in raw:
            if not isinstance(item, str) or "=" not in item:
                return None
            key, value = item.split("=", 1)
            pairs[key] = value
        return pairs

    return {} if raw is None else None


def _networks(service) -> list:
    if service.get("network_mode"):
        return [service["network_mode"]]

    networks = service.get("networks") or {}

    return list(networks.keys()) if isinstance(networks, dict) else list(networks) if isinstance(networks, list) else []


def describe(service: dict, raw_text: str = "") -> dict:
    """The service in the shape the form uses, plus the sections the form cannot edit without losing information."""

    unrepresentable = []

    ports = service.get("ports") or []
    if all(isinstance(p, (str, int)) for p in ports):
        ports = [str(p) for p in ports]
    else:
        ports, unrepresentable = [], unrepresentable + ["ports"]

    volumes = service.get("volumes") or []
    if all(isinstance(v, str) for v in volumes):
        volumes = list(volumes)
    else:
        volumes, unrepresentable = [], unrepresentable + ["volumes"]

    environment = _env_pairs(service.get("environment"))
    if environment is None:
        environment, unrepresentable = {}, unrepresentable + ["environment"]

    if _has_merge_keys(raw_text):
        unrepresentable = list(SECTIONS)

    return {
        "ports": ports,
        "volumes": volumes,
        "environment": environment,
        "networks": _networks(service),
        "capabilities": list(service.get("cap_add") or []),
        "privileged": bool(service.get("privileged", False)),
        "restartPolicy": service.get("restart") or "no",
        "unrepresentable": unrepresentable,
    }


def read_installed_config(container_name) -> dict:
    path = installed_compose_path(container_name)

    with open(path, "r") as file:
        text = file.read()

    try:
        yml_data = yaml.safe_load(text)
    except yaml.YAMLError:
        raise InstalledConfigError("Invalid YML", 500)

    name, service = pick_main(yml_data)

    if not name:
        raise InstalledConfigError("No service data found", 404)

    services = yml_data["services"]
    labels = service.get("labels") or {}

    return {**describe(service, text), "service": name, "ymlContent": yaml.dump(yml_data, sort_keys=False), "warnings": compose_warnings(text), "dependencies": [n for n, s in services.items() if isinstance(s, dict) and (s.get("labels") or {}).get("HDRole") == "dependency"], "hd_group": labels.get("HDGroup"), "hd_role": labels.get("HDRole")}


# --- merging ---


def _resolve(value: str) -> str:
    return process_devhooks(value)[0]


def _list_changes(before, after):
    removed = [item for item in before if item not in after]
    added = [item for item in after if item not in before]

    return removed, added, [item if item in before else _resolve(item) for item in after]


def _outside_app_storage(path):
    from pymodules.hd_DisksPlusAuth import matching_danger_zone

    if not path.startswith("/"):
        return None

    roots = [r.rstrip("/") for r in (get_config_path(), get_internal_storage_path()) if r]

    if any(path == root or path.startswith(root + "/") for root in roots):
        return None

    return matching_danger_zone(path)


def _check_volumes(added, container_name):
    for entry in added:
        source = entry.split(":", 1)[0]
        zone = _outside_app_storage(source)

        if zone:
            raise InstalledConfigError(f"Volume '{entry}' mounts a protected system path ({zone}). Choose a path under the app's storage folders.", 400, section="volumes")


def _check_ports(added, container_name):
    if not added:
        return

    ok, messages, problematic = validate_ports(yaml.dump({"services": {"x": {"ports": added}}}), allow_container_name=container_name)

    if not ok:
        raise InstalledConfigError("Port validation failed", 400, messages=messages, problematic_ports=problematic, section="ports")


def _merge_env(service, current, wanted):
    for key in wanted:
        if key not in current or current[key] != wanted[key]:
            if not isinstance(key, str) or not ENV_NAME.match(key):
                raise InstalledConfigError(f"'{key}' is not a valid environment variable name.", 400, section="environment")

    resolved = {key: (value if key in current and current[key] == value else _resolve(str(value))) for key, value in wanted.items()}
    raw = service.get("environment")

    if isinstance(raw, list):
        original = {item.split("=", 1)[0]: item for item in raw}
        service["environment"] = [original[key] if key in original and current.get(key) == resolved[key] else f"{key}={resolved[key]}" for key in resolved]
    else:
        original = raw or {}
        service["environment"] = {key: original[key] if key in original and current.get(key) == resolved[key] else resolved[key] for key in resolved}

    changes = []
    for key in current:
        if key not in wanted:
            changes.append({"section": "environment", "kind": "removed", "item": key})
    for key, value in wanted.items():
        masked = bool(SECRET_NAME.search(key))
        if key not in current:
            changes.append({"section": "environment", "kind": "added", "item": key, "after": MASK if masked else value})
        elif current[key] != value:
            changes.append({"section": "environment", "kind": "changed", "item": key, "before": MASK if masked else current[key], "after": MASK if masked else value})

    return changes


def _merge_networks(service, yml_data, current, wanted):
    single = len(wanted) == 1 and wanted[0] in NETWORK_MODES
    previous = service.get("networks") if isinstance(service.get("networks"), dict) else {}

    service.pop("network_mode", None)
    service.pop("networks", None)

    changes = []

    if single:
        service["network_mode"] = wanted[0]

        if wanted[0] == "host" and service.get("ports"):
            service["ports"] = []
            changes.append({"section": "ports", "kind": "cleared", "item": "published ports", "note": "Host networking ignores published ports"})
    elif wanted:
        service["networks"] = {name: previous.get(name) or {} for name in wanted}
        declared = yml_data.setdefault("networks", {})

        for name in wanted:
            declared.setdefault(name, {"name": name})

    return changes


def apply_form(yml_data: dict, service_name: str, form: dict, container_name: str, raw_text: str = "") -> list:
    """Writes the touched sections of the form into the parsed compose and returns what changed; untouched sections are left exactly as they were."""

    service = yml_data["services"][service_name]
    current = describe(service, raw_text)
    changes = []

    for section in current["unrepresentable"]:
        if section in form and form[section] != current[section]:
            raise InstalledConfigError(f"'{section}' uses a format the form cannot edit safely. Use the YAML editor for it.", 400, section=section)

    if "ports" in form and form["ports"] != current["ports"] and "ports" not in current["unrepresentable"]:
        wanted = [str(p) for p in form["ports"]]
        removed, added, resolved = _list_changes(current["ports"], wanted)
        _check_ports([p for p in resolved if p not in current["ports"]], container_name)
        added = [p for p in resolved if p not in current["ports"]]
        service["ports"] = resolved
        changes += [{"section": "ports", "kind": "removed", "item": p} for p in removed] + [{"section": "ports", "kind": "added", "item": p} for p in added]

    if "volumes" in form and form["volumes"] != current["volumes"] and "volumes" not in current["unrepresentable"]:
        wanted = [str(v) for v in form["volumes"]]
        removed, added, resolved = _list_changes(current["volumes"], wanted)
        _check_volumes([v for v in resolved if v not in current["volumes"]], container_name)
        added = [v for v in resolved if v not in current["volumes"]]
        service["volumes"] = resolved
        changes += [{"section": "volumes", "kind": "removed", "item": v} for v in removed] + [{"section": "volumes", "kind": "added", "item": v} for v in added]

    if "environment" in form and form["environment"] != current["environment"] and "environment" not in current["unrepresentable"]:
        wanted = {str(k): str(v) for k, v in (form["environment"] or {}).items()}
        changes += _merge_env(service, current["environment"], wanted)

    if "networks" in form and form["networks"] != current["networks"]:
        wanted = [str(n) for n in form["networks"]]
        changes.append({"section": "networks", "kind": "changed", "before": current["networks"], "after": wanted})
        changes += _merge_networks(service, yml_data, current["networks"], wanted)

    if "capabilities" in form and form["capabilities"] != current["capabilities"]:
        wanted = [str(c) for c in form["capabilities"]]
        if wanted:
            service["cap_add"] = wanted
        else:
            service.pop("cap_add", None)
        changes += [{"section": "capabilities", "kind": "removed", "item": c} for c in current["capabilities"] if c not in wanted] + [{"section": "capabilities", "kind": "added", "item": c} for c in wanted if c not in current["capabilities"]]

    if "privileged" in form and bool(form["privileged"]) != current["privileged"]:
        if form["privileged"]:
            service["privileged"] = True
        else:
            service.pop("privileged", None)
        changes.append({"section": "privileged", "kind": "changed", "before": current["privileged"], "after": bool(form["privileged"])})

    if "restartPolicy" in form and form["restartPolicy"] != current["restartPolicy"]:
        service["restart"] = str(form["restartPolicy"])
        changes.append({"section": "restartPolicy", "kind": "changed", "before": current["restartPolicy"], "after": str(form["restartPolicy"])})

    return changes


def update_installed_config(container_name, form, apply: bool) -> dict:
    path = installed_compose_path(container_name)

    with open(path, "r") as file:
        text = file.read()

    try:
        yml_data = yaml.safe_load(text)
    except yaml.YAMLError:
        raise InstalledConfigError("Invalid YML", 500)

    name, _ = pick_main(yml_data)

    if not name:
        raise InstalledConfigError("No service data found", 404)

    if not isinstance(form, dict):
        raise InstalledConfigError("Invalid form")

    changes = apply_form(yml_data, name, form, container_name, text)
    content = yaml.dump(yml_data, sort_keys=False)

    if apply and changes:
        with open(path, "w") as file:
            file.write(content)

    return {"changes": changes, "ymlContent": content, "applied": bool(apply and changes)}


# --- views ---


@login_required
def get_installed_config():
    try:
        return jsonify({"success": True, "data": read_installed_config(request.args.get("containerName"))})
    except InstalledConfigError as e:
        return jsonify(e.payload()), e.status


@login_required
def update_installed_config_view():
    body = request.get_json(silent=True) or {}

    try:
        result = update_installed_config(body.get("containerName"), body.get("form"), bool(body.get("apply")))
    except InstalledConfigError as e:
        return jsonify(e.payload()), e.status

    return jsonify({"success": True, **result})

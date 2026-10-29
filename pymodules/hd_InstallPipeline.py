"""
hd_InstallPipeline.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import os
import json
import yaml
import hashlib
import threading

from pymodules.hd_FunctionsGlobals import current_directory, compose_upload_folder, user_packages_install_folder, user_packages_available_folder
from pymodules.hd_FunctionsMain import copy_file
from pymodules.hd_FunctionsNativeSSL import ssl_enabled
from pymodules.hd_ComposeDevHooks import process_devhooks
from pymodules.hd_HDSPackageManager import normalize_app_slug
from pymodules.hd_PortValidator import validate_ports
from pymodules.hd_ClassDockerComposeHelper import DockerComposeHelper

# the enterprise loader (hd_EnterpriseLoader) only verifies and loads its own signed __Enterprise__ module at startup; it never touches this path

PLACEHOLDER_SUBSTITUTIONS = (("[[HD_USER_NAME]]", "userName"), ("[[HD_PASSWORD]]", "userPassword"), ("[[HD_RND_STR]]", "userRandomString"))
NETWORK_MODES = ("host", "bridge", "none")


class InstallError(Exception):
    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra

    def payload(self):
        return {"success": False, "message": self.message, **self.extra}


# --- source resolution and signature ---


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_hash_folder(s: str) -> bool:
    return len(s) == 16 and all(c in "0123456789abcdef" for c in s.lower())


def resolve_source_yml(container_name: str) -> str:
    """The compose file an install starts from: the bundled store, then imported packages."""

    store = os.path.join(current_directory, "app-store")
    candidates = []

    if ssl_enabled():
        candidates.append(os.path.join(store, "ssl", f"{container_name}.yml"))

    candidates.append(os.path.join(store, f"{container_name}.yml"))
    candidates.append(os.path.join(user_packages_available_folder, f"{container_name}.yml"))

    if " " in container_name:
        candidates.append(os.path.join(user_packages_available_folder, f"{normalize_app_slug(container_name)}.yml"))

    for path in candidates:
        if os.path.exists(path):
            return path

    raise InstallError("Container not found", 404)


def verify_stored_package(source_path: str):
    """An imported package must still match the signature recorded when it was extracted; bundled store apps are not covered."""

    if os.path.dirname(os.path.abspath(source_path)) != os.path.abspath(user_packages_available_folder):
        return

    try:
        with open(f"{source_path}.metadata", "r", encoding="utf-8") as f:
            recorded = json.load(f).get("compose_sha256")
        with open(source_path, "rb") as f:
            current = _sha256(f.read())
    except (OSError, ValueError, AttributeError):
        raise InstallError("This package's signature could not be verified. Remove it and import it again.", 409)

    if not recorded or recorded != current:
        raise InstallError("This package changed after it was imported and no longer matches its signature. Remove it and import it again.", 409)


# --- building the compose to install ---


def _validated(yml_str: str) -> bytes:
    is_valid, messages, problematic_ports = validate_ports(yml_str, allow_container_name=None)

    if not is_valid:
        raise InstallError("Port validation failed", 400, messages=messages, problematic_ports=problematic_ports)

    return yml_str.encode("utf-8")


def build_advanced(yml_content) -> bytes:
    if not yml_content:
        raise InstallError("Missing YML content for advanced configuration")

    try:
        parsed = yaml.safe_load(yml_content)
    except yaml.YAMLError as e:
        raise InstallError(f"Invalid YML content provided: {str(e)}")

    yml_str, _ = process_devhooks(yaml.dump(parsed))

    return _validated(yml_str)


def _read_env(raw) -> dict:
    env = {}

    if isinstance(raw, dict):
        env = {key: str(value) for key, value in raw.items()}
    elif isinstance(raw, list):
        for item in raw:
            if "=" in item:
                key, value = item.split("=", 1)
                env[key] = value

    return env


def build_simple(source_path: str, options: dict) -> bytes:
    volumes = options.get("volumes", [])
    ports = options.get("ports", [])
    networks = options.get("networks", [])
    environment = options.get("environment", {})
    capabilities = options.get("capabilities", [])
    privileged = options.get("privileged", False)
    restart_policy = options.get("restartPolicy", "unless-stopped")

    try:
        with open(source_path, "r") as file:
            yml_str = file.read()
    except OSError as e:
        raise InstallError(f"Error reading original YML: {str(e)}", 500)

    for placeholder, key in PLACEHOLDER_SUBSTITUTIONS:
        if placeholder in yml_str and options.get(key):
            yml_str = yml_str.replace(placeholder, options[key])

    try:
        yml_str, _ = process_devhooks(yml_str, generate_passwords=True)
        yml_data = yaml.safe_load(yml_str)
    except yaml.YAMLError as e:
        raise InstallError(f"Error parsing YML: {str(e)}", 500)

    services = yml_data.get("services", {})
    first_name, first_data = next(iter(services.items()), (None, None))

    if not first_name:
        raise InstallError("No services found in the original YML", 500)

    if any("HDGroup" in service.get("labels", {}) for service in services.values()):
        group = first_data.get("labels", {}).get("HDGroup")
        to_update = [(name, data) for name, data in services.items() if data.get("labels", {}).get("HDGroup") == group]
    else:
        to_update = [(first_name, first_data)]

    single_mode = bool(networks) and len(networks) == 1 and networks[0] in NETWORK_MODES

    for name, data in to_update:
        data.pop("network_mode", None)
        data.pop("networks", None)

        if networks:
            if single_mode:
                data["network_mode"] = networks[0]

                if networks[0] == "host" and name == first_name:
                    data["ports"] = []
            else:
                data["networks"] = {net: {} for net in networks}

    if not (single_mode and networks[0] == "host"):
        first_data["ports"] = ports

    first_data["volumes"] = volumes
    first_data["restart"] = restart_policy

    merged_env = _read_env(first_data.get("environment", {}))
    merged_env.update(environment or {})
    first_data["environment"] = merged_env

    if capabilities:
        first_data["cap_add"] = capabilities

    if privileged:
        first_data["privileged"] = privileged

    if networks and not single_mode:
        declared = yml_data.setdefault("networks", {})

        for network in networks:
            declared.setdefault(network, {"name": network})

    yml_str, _ = process_devhooks(yaml.dump(yml_data))

    return _validated(yml_str)


# --- staging ---

_staged = {}
_staged_lock = threading.Lock()


def staged_path(content_hash: str, user_name: str, container_name: str) -> str:
    return os.path.join(user_packages_install_folder, content_hash, f"{user_name}_{container_name.lower()}.yml")


def stage_config(user_name: str, container_name: str, config_type: str, options: dict) -> str:
    """Builds the compose for an install and stages it under its content hash; returns the hash."""

    source = resolve_source_yml(container_name)
    verify_stored_package(source)

    if config_type == "advanced":
        yml_bytes = build_advanced(options.get("ymlContent"))
    elif config_type == "simple":
        yml_bytes = build_simple(source, options)
    else:
        raise InstallError("Invalid configuration type provided")

    content_hash = _sha256(yml_bytes)[:16]
    path = staged_path(content_hash, user_name, container_name)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as file:
        file.write(yml_bytes)

    with _staged_lock:
        _staged[(user_name, container_name)] = content_hash

    return content_hash


def find_staged(user_name: str, container_name: str, content_hash=None):
    """The staged compose for this install, found by exact hash: the one given, else the one last staged for this user and app."""

    if content_hash is None:
        with _staged_lock:
            content_hash = _staged.get((user_name, container_name))

    if not content_hash or not is_hash_folder(content_hash):
        raise InstallError("Nothing is staged for this installation. Open the install window again and retry.", 404)

    path = staged_path(content_hash, user_name, container_name)

    if not os.path.isfile(path):
        raise InstallError("The staged configuration for this installation was not found. Open the install window again and retry.", 404)

    with open(path, "rb") as file:
        if _sha256(file.read())[:16] != content_hash:
            discard_staged(content_hash, user_name, container_name)
            raise InstallError("The staged configuration no longer matches its hash. Open the install window again and retry.", 409)

    return path


def discard_staged(content_hash: str, user_name: str, container_name: str):
    """Removes this app's staged file; the folder goes only when no other app's file shares it."""

    path = staged_path(content_hash, user_name, container_name)

    try:
        os.remove(path)
    except OSError:
        pass

    try:
        os.rmdir(os.path.dirname(path))
    except OSError:
        pass

    with _staged_lock:
        if _staged.get((user_name, container_name)) == content_hash:
            del _staged[(user_name, container_name)]


# --- the queue ---

_queue = []
_errors = {}
_worker_running = False
_lock = threading.Lock()

ERROR_HINTS = (
    (lambda e: "no matching manifest" in e, "This app is not compatible with your system architecture."),
    (lambda e: "tls" in e or "x509" in e or "certificate" in e, "TLS/certificate error pulling images. Check your network, DNS, or proxy settings."),
    (lambda e: "timeout" in e, "Installation timed out. Check your internet connection and try again."),
    (lambda e: "network" in e or "connection refused" in e, "Network error during installation. Check your internet connection."),
    (lambda e: "unauthorized" in e or "authentication required" in e, "Authentication failed. The image may require Docker Hub login."),
    (lambda e: "not found" in e and "manifest" in e, "Image not found. The Docker image may have been removed or renamed."),
    (lambda e: "permission denied" in e, "Permission denied. Check Docker permissions."),
    (lambda e: "disk" in e or "no space" in e, "Not enough disk space to install this app."),
)


def explain_failure(message) -> str:
    text = str(message).lower() if message else ""

    return next((hint for matches, hint in ERROR_HINTS if matches(text)), "Installation failed. Check terminal logs for details.")


def _record_error(container_name: str, message: str):
    with _lock:
        _errors[container_name] = message


def _install_one(job: dict):
    name, user, content_hash = job["container"], job["user"], job["hash"]

    try:
        compose_file = find_staged(user, name, content_hash)
    except InstallError as e:
        print(f"[AppStore] ERROR: {e.message} ({name})")
        _record_error(name, e.message)
        return

    try:
        success, message = DockerComposeHelper.get_instance().up(compose_file=compose_file, detach=True)

        if not success:
            print(f"[AppStore] ERROR installing {name}: {message}")
            _record_error(name, explain_failure(message))
            return

        os.makedirs(compose_upload_folder, exist_ok=True)
        copy_file(compose_file, os.path.join(compose_upload_folder, f"{name}.yml"))
    except Exception as e:
        print(f"[AppStore] Exception: {e}")
        _record_error(name, "Installation failed. Check terminal logs for details.")
    finally:
        discard_staged(content_hash, user, name)


def enqueue_install(user_name: str, container_name: str, content_hash=None):
    """Queues an install; the caller that finds no worker running becomes the worker and returns once the queue drains."""

    global _worker_running

    path = find_staged(user_name, container_name, content_hash)
    content_hash = os.path.basename(os.path.dirname(path))

    with _lock:
        if any(job["container"] == container_name for job in _queue):
            return

        _queue.append({"container": container_name, "user": user_name, "hash": content_hash})

        if _worker_running:
            return

        _worker_running = True

    while True:
        with _lock:
            if not _queue:
                _worker_running = False
                return

            job = _queue[0]

        try:
            _install_one(job)
        finally:
            with _lock:
                _queue.pop(0)


def installation_status():
    with _lock:
        names = [job["container"] for job in _queue]
        errors = dict(_errors)
        _errors.clear()

    return {"currently_installing": names[0] if names else None, "queue": names[1:], "errors": errors}

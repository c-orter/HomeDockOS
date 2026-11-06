"""
hd_UITrash.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import os
import time
import shutil
import threading

from datetime import datetime
from urllib.parse import quote, unquote

from flask import jsonify, request
from flask_login import current_user, login_required

from pymodules.hd_FunctionsGlobals import storage_folder, dropzone_folder
from pymodules.hd_FunctionsSecurity import validate_safe_path, validate_no_symlinks, calculate_directory_size_ddos_safe

TRASH_DIR = ".Trash"
INFO_SUFFIX = ".trashinfo"
RETENTION_SECONDS = 30 * 24 * 60 * 60
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
MAX_BATCH = 1000

LOCATIONS = {"storage": storage_folder, "dropzone": dropzone_folder}


class TrashError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _user_dir(location, user_name):
    return os.path.join(LOCATIONS[location], user_name)


def _trash_paths(user_dir):
    root = os.path.join(user_dir, TRASH_DIR)
    return root, os.path.join(root, "files"), os.path.join(root, "info")


def _ensure_trash(user_dir):
    root, files_dir, info_dir = _trash_paths(user_dir)
    for path in (root, files_dir, info_dir):
        os.makedirs(path, mode=0o700, exist_ok=True)
        if os.path.islink(path):
            raise TrashError("Security violation", 403)
    return files_dir, info_dir


def is_inside_trash(user_dir, path):
    root = os.path.realpath(os.path.join(user_dir, TRASH_DIR))
    real = os.path.realpath(path)
    return real == root or real.startswith(root + os.sep)


def _remove_path(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)


def _split_name(name, is_directory):
    if is_directory:
        return name, ""
    base, ext = os.path.splitext(name)
    return (base, ext) if base else (name, "")


def _reserve_info(info_dir, files_dir, name, is_directory):
    base, ext = _split_name(name, is_directory)
    candidate = name
    counter = 2
    while True:
        info_path = os.path.join(info_dir, candidate + INFO_SUFFIX)
        if not os.path.lexists(os.path.join(files_dir, candidate)):
            try:
                fd = os.open(info_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                return candidate, fd
            except FileExistsError:
                pass
        candidate = f"{base} ({counter}){ext}"
        counter += 1


def _read_info(info_path):
    original = None
    deleted_at = None
    try:
        with open(info_path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if not lines or lines[0].strip() != "[Trash Info]":
        return None
    for line in lines[1:]:
        key, _, value = line.partition("=")
        if key == "Path":
            original = unquote(value)
        elif key == "DeletionDate":
            try:
                deleted_at = datetime.strptime(value.strip(), DATE_FORMAT).timestamp()
            except ValueError:
                deleted_at = None
    if not original:
        return None
    if deleted_at is None:
        try:
            deleted_at = os.path.getmtime(info_path)
        except OSError:
            deleted_at = time.time()
    return original, deleted_at


def _check_deletable(user_dir, file_path):
    if os.path.realpath(file_path) == os.path.realpath(user_dir):
        raise TrashError("Invalid file path")
    if is_inside_trash(user_dir, file_path):
        raise TrashError("Items in the Trash cannot be moved to the Trash")


def delete_permanently(user_dir, file_path):
    _check_deletable(user_dir, file_path)
    try:
        _remove_path(file_path)
    except OSError:
        raise TrashError("Error deleting item", 500)


def remove_item(user_dir, file_path, permanent):
    if permanent:
        delete_permanently(user_dir, file_path)
        return {"success": True}
    move_to_trash(user_dir, file_path)
    return {"success": True, "trashed": True}


def move_to_trash(user_dir, file_path):
    _check_deletable(user_dir, file_path)

    purge_expired(user_dir)
    files_dir, info_dir = _ensure_trash(user_dir)

    original = os.path.relpath(file_path, user_dir).replace("\\", "/")
    name, fd = _reserve_info(info_dir, files_dir, os.path.basename(file_path), os.path.isdir(file_path))
    info_path = os.path.join(info_dir, name + INFO_SUFFIX)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"[Trash Info]\nPath={quote(original)}\nDeletionDate={datetime.now().strftime(DATE_FORMAT)}\n")
        os.replace(file_path, os.path.join(files_dir, name))
    except OSError:
        try:
            os.remove(info_path)
        except OSError:
            pass
        raise TrashError("Error moving item to the Trash", 500)

    return name


def purge_expired(user_dir, now=None):
    _, files_dir, info_dir = _trash_paths(user_dir)
    if not os.path.isdir(info_dir) or os.path.islink(info_dir):
        return
    cutoff = (now or time.time()) - RETENTION_SECONDS
    try:
        entries = list(os.scandir(info_dir))
    except OSError:
        return
    for entry in entries:
        if not entry.name.endswith(INFO_SUFFIX) or not entry.is_file(follow_symlinks=False):
            continue
        name = entry.name[: -len(INFO_SUFFIX)]
        stored = os.path.join(files_dir, name)
        info = _read_info(entry.path)
        expired = info is None or info[1] < cutoff
        if not expired and os.path.lexists(stored):
            continue
        try:
            _remove_path(stored)
            os.remove(entry.path)
        except OSError:
            continue


def purge_all_users():
    for base in LOCATIONS.values():
        try:
            entries = list(os.scandir(base))
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith((".", "_")) or not entry.is_dir(follow_symlinks=False):
                continue
            purge_expired(entry.path)


def start_trash_purge():
    threading.Thread(target=purge_all_users, daemon=True, name="hdos-trash-purge").start()


def _list_location(location, user_name):
    user_dir = _user_dir(location, user_name)
    purge_expired(user_dir)
    _, files_dir, info_dir = _trash_paths(user_dir)
    if not os.path.isdir(info_dir) or os.path.islink(info_dir):
        return []

    items = []
    for entry in os.scandir(info_dir):
        if not entry.name.endswith(INFO_SUFFIX) or not entry.is_file(follow_symlinks=False):
            continue
        name = entry.name[: -len(INFO_SUFFIX)]
        stored = os.path.join(files_dir, name)
        if not os.path.lexists(stored) or os.path.islink(stored):
            continue
        info = _read_info(entry.path)
        if info is None:
            continue
        original, deleted_at = info
        is_directory = os.path.isdir(stored)
        try:
            if is_directory:
                size, size_exceeded = calculate_directory_size_ddos_safe(stored)
            else:
                size, size_exceeded = os.path.getsize(stored), False
        except OSError:
            continue
        items.append(
            {
                "id": f"{location}:{name}",
                "location": location,
                "stored_name": name,
                "name": os.path.basename(original),
                "original_path": original,
                "deleted_at": deleted_at,
                "expires_at": deleted_at + RETENTION_SECONDS,
                "size": size,
                "size_exceeded": size_exceeded,
                "is_directory": is_directory,
            }
        )
    return items


def _resolve_item(item_id, user_name):
    if not isinstance(item_id, str) or ":" not in item_id:
        raise TrashError("Invalid item")
    location, _, name = item_id.partition(":")
    if location not in LOCATIONS or not name or "/" in name or "\\" in name or "\x00" in name or name in (".", ".."):
        raise TrashError("Invalid item")
    user_dir = _user_dir(location, user_name)
    _, files_dir, info_dir = _trash_paths(user_dir)
    stored = os.path.join(files_dir, name)
    info_path = os.path.join(info_dir, name + INFO_SUFFIX)
    if not os.path.lexists(stored) or not os.path.isfile(info_path):
        raise TrashError("Item not found", 404)
    try:
        validate_no_symlinks(stored, user_dir)
        validate_no_symlinks(info_path, user_dir)
    except ValueError:
        raise TrashError("Security violation", 403)
    return location, user_dir, stored, info_path


def _free_destination(path, is_directory):
    if not os.path.lexists(path):
        return path
    parent, name = os.path.split(path)
    base, ext = _split_name(name, is_directory)
    counter = 2
    while True:
        candidate = os.path.join(parent, f"{base} ({counter}){ext}")
        if not os.path.lexists(candidate):
            return candidate
        counter += 1


def _restore_item(item_id, user_name):
    location, user_dir, stored, info_path = _resolve_item(item_id, user_name)
    info = _read_info(info_path)
    if info is None:
        raise TrashError("The original location of this item is unknown", 409)

    try:
        destination = validate_safe_path(user_dir, info[0])
    except ValueError:
        raise TrashError("The original location of this item is unknown", 409)
    if is_inside_trash(user_dir, destination) or os.path.realpath(destination) == os.path.realpath(user_dir):
        raise TrashError("The original location of this item is unknown", 409)

    parent = os.path.dirname(destination)
    try:
        os.makedirs(parent, mode=0o700, exist_ok=True)
        validate_no_symlinks(parent, user_dir)
    except ValueError:
        raise TrashError("Security violation", 403)
    except OSError:
        raise TrashError("Cannot recreate the original folder", 500)

    destination = _free_destination(destination, os.path.isdir(stored))
    try:
        os.replace(stored, destination)
        os.remove(info_path)
    except OSError:
        raise TrashError("Error restoring item", 500)

    return {"id": item_id, "location": location, "path": os.path.relpath(destination, user_dir).replace("\\", "/")}


def _delete_item(item_id, user_name):
    _, _, stored, info_path = _resolve_item(item_id, user_name)
    try:
        _remove_path(stored)
        os.remove(info_path)
    except OSError:
        raise TrashError("Error deleting item", 500)


def _batch_ids():
    body = request.get_json(silent=True) or {}
    ids = body.get("items")
    if not isinstance(ids, list) or not ids or len(ids) > MAX_BATCH:
        raise TrashError("No items specified")
    return ids


@login_required
def trash_list():
    user_name = current_user.id.lower()
    items = []
    for location in LOCATIONS:
        try:
            items.extend(_list_location(location, user_name))
        except OSError:
            continue
    items.sort(key=lambda item: item["deleted_at"], reverse=True)
    return jsonify({"items": items, "total_size": sum(item["size"] for item in items), "retention_days": RETENTION_SECONDS // 86400})


@login_required
def trash_restore():
    user_name = current_user.id.lower()
    try:
        ids = _batch_ids()
    except TrashError as e:
        return jsonify({"error": e.message}), e.status

    restored, failed = [], []
    for item_id in ids:
        try:
            restored.append(_restore_item(item_id, user_name))
        except TrashError as e:
            failed.append({"id": item_id, "error": e.message})
    return jsonify({"success": not failed, "restored": restored, "failed": failed})


@login_required
def trash_delete():
    user_name = current_user.id.lower()
    try:
        ids = _batch_ids()
    except TrashError as e:
        return jsonify({"error": e.message}), e.status

    deleted, failed = [], []
    for item_id in ids:
        try:
            _delete_item(item_id, user_name)
            deleted.append(item_id)
        except TrashError as e:
            failed.append({"id": item_id, "error": e.message})
    return jsonify({"success": not failed, "deleted": deleted, "failed": failed})


@login_required
def trash_empty():
    user_name = current_user.id.lower()
    failed = False
    for location in LOCATIONS:
        user_dir = _user_dir(location, user_name)
        root, _, _ = _trash_paths(user_dir)
        if not os.path.lexists(root):
            continue
        try:
            validate_no_symlinks(root, user_dir)
            _remove_path(root)
        except (ValueError, OSError):
            failed = True
    if failed:
        return jsonify({"error": "Error emptying the Trash"}), 500
    return jsonify({"success": True})

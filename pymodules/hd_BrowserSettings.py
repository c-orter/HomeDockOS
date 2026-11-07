"""
hd_BrowserSettings.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro

The browser's settings live in their own file, not in homedock_server.conf: saving the general settings rewrites that
whole file from a fixed list of keys, which would silently drop anything added to it.
"""

import json
import os
import tempfile
import threading

from pymodules.hd_FunctionsGlobals import user_packages_folder

BROWSER_FOLDER = os.path.join(user_packages_folder, "_browser")
SETTINGS_FILE = os.path.join(BROWSER_FOLDER, "settings.json")

DEFAULTS = {"idle_minutes": 15, "memory_mb": 2048, "cpus": 1.0, "pids": 512}

# (low, high) inclusive. Memory is also the ceiling the container may use; the shared-memory area gets half of it.
RANGES = {"idle_minutes": (1, 1440), "memory_mb": (512, 16384), "cpus": (0.5, 8.0), "pids": (128, 4096)}

_lock = threading.Lock()


class SettingsError(Exception):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field
        self.message = message


def _number(field, value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise SettingsError(field, "Enter a number.")

    try:
        number = float(value)
    except ValueError:
        raise SettingsError(field, "Enter a number.")

    if number != number or number in (float("inf"), float("-inf")):
        raise SettingsError(field, "Enter a number.")

    return number


def validate(payload):
    """The cleaned values for every field present in the payload. The first bad field raises SettingsError with a message to show."""

    if not isinstance(payload, dict):
        raise SettingsError("", "Send the settings as an object.")

    clean = {}

    for field, (low, high) in RANGES.items():
        if field not in payload:
            continue

        number = _number(field, payload[field])

        if not low <= number <= high:
            raise SettingsError(field, f"Use a value between {low:g} and {high:g}.")

        if field == "cpus":
            clean[field] = round(number * 2) / 2
        else:
            if number != int(number):
                raise SettingsError(field, "Use a whole number.")

            clean[field] = int(number)

    return clean


def load():
    """Saved settings over the defaults. A missing or damaged file, or a value outside its range, falls back to the default for that field."""

    values = dict(DEFAULTS)

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
            saved = json.load(handle)
    except (OSError, ValueError):
        return values

    if isinstance(saved, dict):
        for field in RANGES:
            if field not in saved:
                continue

            try:
                values.update(validate({field: saved[field]}))
            except SettingsError:
                pass

    return values


def save(changes):
    """Validates, merges into what is saved and writes it atomically. Returns the full settings."""

    clean = validate(changes)

    with _lock:
        values = load()
        values.update(clean)

        os.makedirs(BROWSER_FOLDER, mode=0o700, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=BROWSER_FOLDER, prefix=".settings.")

        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(values, handle)

            os.replace(temporary, SETTINGS_FILE)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass

            raise

    return values


def limits():
    """The container limits the saved settings give, in the form the Docker API takes."""

    values = load()

    return {"mem_limit": f"{values['memory_mb']}m", "shm_size": f"{values['memory_mb'] // 2}m", "pids_limit": values["pids"], "nano_cpus": int(values["cpus"] * 1_000_000_000)}

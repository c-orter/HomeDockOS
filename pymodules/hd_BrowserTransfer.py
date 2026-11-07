"""
hd_BrowserTransfer.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro

Files cross between the browser and the dropzone through the container engine's API. Nothing from the host is mounted
into the browser, so a page that takes over the browser still sees nothing of the host or of other users' files.

Downloads: a finished file in the container's Downloads folder is copied out, encrypted into the user's dropzone under
"Browser", then deleted from the container.
Uploads: the files in the dropzone's "Browser" folder are decrypted into a memory-backed folder in the container
(/tmp/uploads, linked as ~/Uploads), where the browser's file dialog can pick them. They are gone when it stops.
"""

import io
import os
import re
import tarfile
import threading
import time

from pymodules.hd_BrowserEngine import CHROMIUM_USER
from pymodules.hd_FunctionsGlobals import dropzone_folder

FOLDER = "Browser"

MIB = 1024 * 1024

# A download is held in memory while it is encrypted, so one file is capped. The folder cap keeps the browser from
# filling the server's disk through the dropzone.
MAX_FILE_BYTES = 256 * MIB
MAX_FOLDER_BYTES = 1024 * MIB

# Uploads are decrypted into the container's memory-backed /tmp (256 MB), so they are capped well under that.
MAX_UPLOAD_FILE_BYTES = 100 * MIB
MAX_UPLOAD_TOTAL_BYTES = 200 * MIB

UPLOAD_DIR = "/tmp/uploads"
UPLOAD_LINK = "/config/Uploads"

MAX_NOTICES = 50

_state = {"previous": {}, "next_id": 1, "notices": []}
_lock = threading.Lock()
_sync_lock = threading.Lock()

_UNSAFE = re.compile(r'[<>:"|?*\\/\x00-\x1f]')


def notice(kind, name, reason=""):
    with _lock:
        _state["notices"].append({"id": _state["next_id"], "kind": kind, "name": name, "reason": reason, "at": time.time()})
        _state["next_id"] += 1
        del _state["notices"][:-MAX_NOTICES]


def notices_after(last_id):
    with _lock:
        return [dict(n) for n in _state["notices"] if n["id"] > last_id]


def reset():
    with _lock:
        _state.update(previous={}, next_id=1, notices=[])


def reset_previous():
    """Forgets the last look at the Downloads folder, so a restarted browser's files are judged fresh."""

    with _lock:
        _state["previous"] = {}


def safe_name(raw):
    """A name for the dropzone from whatever a web page called the file."""

    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    text = _UNSAFE.sub("_", text).strip().lstrip(".").rstrip(". ")

    if len(text) > 200:
        stem, extension = os.path.splitext(text)
        text = stem[: 200 - len(extension)] + extension

    return text or "download"


def unique_name(directory, name):
    if not os.path.exists(os.path.join(directory, name)):
        return name

    stem, extension = os.path.splitext(name)
    number = 1

    while os.path.exists(os.path.join(directory, f"{stem} ({number}){extension}")):
        number += 1

    return f"{stem} ({number}){extension}"


def folder_size(directory):
    total = 0

    for root, _, files in os.walk(directory):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass

    return total


def parse_listing(output):
    """{name: (size, mtime)} from `find -printf '%f\\0%s\\0%T@\\0'`."""

    fields = output.split(b"\0")
    listing = {}

    for i in range(0, len(fields) - 2, 3):
        try:
            listing[fields[i].decode("utf-8", "replace")] = (int(fields[i + 1]), fields[i + 2].decode("latin-1"))
        except ValueError:
            continue

    return listing


def finished(previous, current):
    """Names that are done: not a temporary Chromium file, and unchanged since the last look."""

    return [
        name
        for name, seen in current.items()
        if not name.startswith(".") and not name.endswith(".crdownload") and f"{name}.crdownload" not in current and previous.get(name) == seen
    ]


def list_downloads(container, directory):
    result = container.exec_run(["find", directory, "-maxdepth", "1", "-type", "f", "-printf", "%f\\0%s\\0%T@\\0"], user=CHROMIUM_USER)

    return parse_listing(result.output) if result.exit_code == 0 else {}


def read_file(container, path, limit):
    stream, _ = container.get_archive(path)
    buffer = io.BytesIO()

    for chunk in stream:
        buffer.write(chunk)

        if buffer.tell() > limit + 1024 * 1024:
            raise ValueError("larger than expected")

    buffer.seek(0)

    with tarfile.open(fileobj=buffer, mode="r:") as archive:
        member = next((m for m in archive.getmembers() if m.isfile()), None)

        if member is None:
            raise ValueError("not a file")

        return archive.extractfile(member).read()


def _discard(container, path):
    container.exec_run(["rm", "-f", "--", path], user=CHROMIUM_USER)


def ingest(container, directory, name, size, username, save=None):
    """Moves one finished download into the dropzone, or discards it with a notice saying why."""

    from pymodules.hd_DropZoneEncryption import save_user_file

    save = save or save_user_file
    path = f"{directory}/{name}"
    target_dir = os.path.join(dropzone_folder, username, FOLDER)

    if size > MAX_FILE_BYTES:
        _discard(container, path)
        notice("rejected", name, f"It is larger than the {MAX_FILE_BYTES // MIB} MB limit for one file.")
        return False

    if folder_size(target_dir) + size > MAX_FOLDER_BYTES:
        _discard(container, path)
        notice("rejected", name, f"The Browser folder in your dropzone would pass its {MAX_FOLDER_BYTES // MIB} MB limit. Delete some files there and download it again.")
        return False

    try:
        data = read_file(container, path, MAX_FILE_BYTES)
    except Exception:
        notice("rejected", name, "It could not be read from the browser.")
        return False

    final = unique_name(target_dir, safe_name(name))
    save(username, f"{FOLDER}/{final}", data)
    _discard(container, path)
    notice("saved", final)

    return True


def sync_downloads(container, directory, username):
    """One pass over the Downloads folder. A file moves only once it has stopped changing between two passes."""

    with _sync_lock:
        current = list_downloads(container, directory)

        with _lock:
            previous = _state["previous"]
            _state["previous"] = current

        moved = 0

        for name in finished(previous, current):
            if ingest(container, directory, name, current[name][0], username):
                moved += 1

        return moved


def build_uploads(username):
    """(tar bytes, skipped names) of the decrypted files in the dropzone's Browser folder, owned by the browser's user."""

    from pymodules.hd_DropZoneEncryption import load_user_file

    source = os.path.join(dropzone_folder, username, FOLDER)
    uid, gid = (int(x) for x in CHROMIUM_USER.split(":"))
    buffer = io.BytesIO()
    skipped = []
    total = 0

    with tarfile.open(fileobj=buffer, mode="w") as archive:
        top = tarfile.TarInfo("uploads")
        top.type = tarfile.DIRTYPE
        top.mode, top.uid, top.gid = 0o755, uid, gid
        archive.addfile(top)

        names = sorted(os.listdir(source)) if os.path.isdir(source) else []

        for name in names:
            path = os.path.join(source, name)

            if name.startswith(".") or os.path.islink(path) or not os.path.isfile(path):
                continue

            if os.path.getsize(path) > MAX_UPLOAD_FILE_BYTES + 1024:
                skipped.append((name, f"It is larger than the {MAX_UPLOAD_FILE_BYTES // MIB} MB limit for uploads."))
                continue

            try:
                data = load_user_file(username, f"{FOLDER}/{name}")
            except Exception:
                skipped.append((name, "It could not be decrypted."))
                continue

            if len(data) > MAX_UPLOAD_FILE_BYTES:
                skipped.append((name, f"It is larger than the {MAX_UPLOAD_FILE_BYTES // MIB} MB limit for uploads."))
                continue

            if total + len(data) > MAX_UPLOAD_TOTAL_BYTES:
                skipped.append((name, f"The Browser folder is over the {MAX_UPLOAD_TOTAL_BYTES // MIB} MB limit for uploads."))
                continue

            total += len(data)
            info = tarfile.TarInfo(f"uploads/{name}")
            info.size = len(data)
            info.mode, info.uid, info.gid = 0o644, uid, gid
            archive.addfile(info, io.BytesIO(data))

    buffer.seek(0)

    return buffer.getvalue(), skipped


def push_uploads(container, username):
    """Replaces the container's upload folder with the dropzone's Browser files. Returns how many were made available."""

    # The folder exists from the first open, so the window's Downloads button always has somewhere to go.
    os.makedirs(os.path.join(dropzone_folder, username, FOLDER), mode=0o700, exist_ok=True)

    archive, skipped = build_uploads(username)

    container.exec_run(["sh", "-c", f"rm -rf {UPLOAD_DIR}"], user=CHROMIUM_USER)
    container.put_archive("/tmp", archive)
    container.exec_run(["sh", "-c", f"ln -sfn {UPLOAD_DIR} {UPLOAD_LINK}"], user=CHROMIUM_USER)

    for name, reason in skipped:
        notice("upload_skipped", name, reason)

    with tarfile.open(fileobj=io.BytesIO(archive)) as listing:
        return sum(1 for m in listing.getmembers() if m.isfile())

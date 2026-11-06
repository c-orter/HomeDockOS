import io
import os
import tarfile
from types import SimpleNamespace

import pytest

from pymodules import hd_BrowserTransfer as transfer
from pymodules import hd_DropZoneEncryption as encryption


@pytest.fixture(autouse=True)
def dropzone(tmp_path, monkeypatch):
    monkeypatch.setattr(transfer, "dropzone_folder", str(tmp_path))
    monkeypatch.setattr(encryption, "dropzone_folder", str(tmp_path))
    monkeypatch.setattr(encryption, "MASTER_KEY_FILE", str(tmp_path / "keys.conf"))
    transfer.reset()

    return tmp_path


def listing(*files):
    return b"".join(f"{name}\0{size}\0{mtime}\0".encode() for name, size, mtime in files)


def tar_of(name, data):
    buffer = io.BytesIO()

    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))

    return buffer.getvalue()


class FakeContainer:
    def __init__(self, files=None):
        self.files = dict(files or {})
        self.commands = []
        self.put = []

    def exec_run(self, cmd, user=None):
        self.commands.append(cmd)

        if cmd[0] == "find":
            return SimpleNamespace(exit_code=0, output=listing(*[(n, len(d), "1.0") for n, d in self.files.items()]))

        if cmd[0] == "rm":
            self.files.pop(cmd[-1].rsplit("/", 1)[-1], None)

        return SimpleNamespace(exit_code=0, output=b"")

    def get_archive(self, path):
        name = path.rsplit("/", 1)[-1]

        return iter([tar_of(name, self.files[name])]), {}

    def put_archive(self, path, data):
        self.put.append((path, data))


def test_a_listing_is_parsed():
    assert transfer.parse_listing(listing(("a.pdf", 10, "5.5"), ("b b.txt", 0, "6"))) == {"a.pdf": (10, "5.5"), "b b.txt": (0, "6")}
    assert transfer.parse_listing(b"") == {}
    assert transfer.parse_listing(b"torn\0") == {}


def test_a_file_is_finished_only_when_it_stopped_changing():
    first = {"a.zip": (10, "1")}

    assert transfer.finished({}, first) == []
    assert transfer.finished(first, first) == ["a.zip"]
    assert transfer.finished(first, {"a.zip": (20, "2")}) == []


def test_unfinished_and_hidden_files_are_left_alone():
    current = {"big.iso": (1, "1"), "big.iso.crdownload": (1, "1"), ".com.google.Chrome.x": (1, "1"), "x.crdownload": (1, "1")}

    assert transfer.finished(current, current) == []


@pytest.mark.parametrize("raw,expected", [("report.pdf", "report.pdf"), ("../../etc/passwd", "_.._etc_passwd"), (".hidden", "hidden"), ("a:b*c?.txt", "a_b_c_.txt"), ("", "download"), ("...", "download"), ("trailing. ", "trailing"), (b"bad\xff.bin", "bad�.bin")])
def test_names_from_a_web_page_are_made_safe(raw, expected):
    assert transfer.safe_name(raw) == expected


def test_a_long_name_keeps_its_extension():
    name = transfer.safe_name("x" * 400 + ".pdf")

    assert len(name) <= 200 and name.endswith(".pdf")


def test_a_clashing_name_gets_a_number(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "a (1).txt").write_text("x")

    assert transfer.unique_name(str(tmp_path), "a.txt") == "a (2).txt"
    assert transfer.unique_name(str(tmp_path), "b.txt") == "b.txt"


def test_a_download_is_encrypted_into_the_dropzone_and_removed_from_the_browser(dropzone):
    container = FakeContainer({"report.pdf": b"PDF DATA"})

    assert transfer.sync_downloads(container, "/config/Downloads", "carter") == 0
    assert transfer.sync_downloads(container, "/config/Downloads", "carter") == 1

    stored = dropzone / "carter" / "Browser" / "report.pdf"

    assert stored.exists() and stored.read_bytes() != b"PDF DATA"
    assert encryption.load_user_file("carter", "Browser/report.pdf") == b"PDF DATA"
    assert container.files == {}
    assert [n["kind"] for n in transfer.notices_after(0)] == ["saved"]


def test_a_file_still_growing_is_not_taken(dropzone):
    container = FakeContainer({"a.bin": b"1"})
    transfer.sync_downloads(container, "/config/Downloads", "carter")
    container.files["a.bin"] = b"12"

    assert transfer.sync_downloads(container, "/config/Downloads", "carter") == 0
    assert container.files


def test_an_oversize_download_is_discarded_with_the_reason(dropzone, monkeypatch):
    monkeypatch.setattr(transfer, "MAX_FILE_BYTES", 4)
    container = FakeContainer({"big.bin": b"12345"})
    transfer.sync_downloads(container, "/config/Downloads", "carter")
    transfer.sync_downloads(container, "/config/Downloads", "carter")

    assert container.files == {}
    assert not (dropzone / "carter" / "Browser").exists()

    (note,) = transfer.notices_after(0)

    assert note["kind"] == "rejected" and note["name"] == "big.bin" and "limit for one file" in note["reason"]


def test_the_folder_cap_stops_a_download_that_would_pass_it(dropzone, monkeypatch):
    monkeypatch.setattr(transfer, "MAX_FOLDER_BYTES", 10)
    folder = dropzone / "carter" / "Browser"
    folder.mkdir(parents=True)
    (folder / "old.bin").write_bytes(b"x" * 8)
    container = FakeContainer({"new.bin": b"abc"})
    transfer.sync_downloads(container, "/config/Downloads", "carter")
    transfer.sync_downloads(container, "/config/Downloads", "carter")

    assert not (folder / "new.bin").exists()
    assert container.files == {}

    (note,) = transfer.notices_after(0)

    assert note["kind"] == "rejected" and "Browser folder" in note["reason"]


def test_a_hostile_name_cannot_leave_the_browser_folder(dropzone):
    container = FakeContainer({"..%2f.bin": b"a", "x": b"b"})
    container.files["a b"] = b"c"
    transfer.sync_downloads(container, "/config/Downloads", "carter")
    transfer.sync_downloads(container, "/config/Downloads", "carter")

    for root, _, files in os.walk(dropzone):
        for f in files:
            assert root.startswith(str(dropzone / "carter" / "Browser")) or f == "keys.conf"


def test_the_browser_gets_only_the_browser_folders_files_as_decrypted_copies(dropzone):
    encryption.save_user_file("carter", "Browser/cv.pdf", b"MY CV")
    encryption.save_user_file("carter", "secret.txt", b"NOT FOR THE BROWSER")
    encryption.save_user_file("someone", "Browser/theirs.txt", b"THEIRS")
    container = FakeContainer()

    assert transfer.push_uploads(container, "carter") == 1

    path, data = container.put[0]

    assert path == "/tmp"

    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        names = [m.name for m in archive.getmembers()]
        member = archive.getmember("uploads/cv.pdf")

        assert names == ["uploads", "uploads/cv.pdf"]
        assert archive.extractfile(member).read() == b"MY CV"
        assert (member.uid, member.gid) == (911, 911)


def test_uploads_live_in_memory_backed_tmp_and_are_linked_into_the_home_folder(dropzone):
    container = FakeContainer()
    transfer.push_uploads(container, "carter")

    assert ["sh", "-c", "rm -rf /tmp/uploads"] in container.commands
    assert ["sh", "-c", "ln -sfn /tmp/uploads /config/Uploads"] in container.commands


def test_oversize_uploads_are_skipped_and_explained(dropzone, monkeypatch):
    monkeypatch.setattr(transfer, "MAX_UPLOAD_FILE_BYTES", 5)
    encryption.save_user_file("carter", "Browser/small.txt", b"ok")
    encryption.save_user_file("carter", "Browser/large.bin", b"x" * 50)

    assert transfer.push_uploads(FakeContainer(), "carter") == 1

    (note,) = transfer.notices_after(0)

    assert note["kind"] == "upload_skipped" and note["name"] == "large.bin"


def test_the_total_upload_size_is_capped(dropzone, monkeypatch):
    monkeypatch.setattr(transfer, "MAX_UPLOAD_TOTAL_BYTES", 6)
    encryption.save_user_file("carter", "Browser/a.txt", b"1234")
    encryption.save_user_file("carter", "Browser/b.txt", b"5678")

    assert transfer.push_uploads(FakeContainer(), "carter") == 1
    assert transfer.notices_after(0)[0]["kind"] == "upload_skipped"


def test_notices_are_numbered_so_a_window_only_sees_new_ones():
    transfer.notice("saved", "a")
    transfer.notice("saved", "b")

    assert [n["name"] for n in transfer.notices_after(0)] == ["a", "b"]
    assert [n["name"] for n in transfer.notices_after(1)] == ["b"]
    assert transfer.notices_after(2) == []


def test_the_browser_container_is_given_no_host_mount():
    from pymodules import hd_BrowserRuntime as runtime
    import inspect

    source = inspect.getsource(runtime._launch)

    assert "volumes={PROFILE_VOLUME" in source
    assert "/var/run/docker.sock" not in source and "dropzone" not in source

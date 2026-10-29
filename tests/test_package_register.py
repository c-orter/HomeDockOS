import base64
import io
import json
import os

import pytest
from flask import Flask

from pymodules import hd_HDSPackageManager as hds
from pymodules import hd_UIAppStoreReadSaveYML as store_view
from pymodules.hd_ComposeWarnings import compose_warnings

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def compose(extra="", name="demo"):
    return f"services:\n  web:\n    image: nginx:alpine\n    container_name: {name}\n{extra}"


@pytest.mark.parametrize(
    "extra,expected",
    [
        ("", []),
        ("    privileged: true\n", ["privileged"]),
        ("    volumes:\n      - /var/run/docker.sock:/var/run/docker.sock\n", ["docker_socket"]),
        ("    volumes:\n      - /run/docker.sock:/s:ro\n", ["docker_socket"]),
        ("    volumes:\n      - /:/host\n", ["host_root"]),
        ("    volumes:\n      - type: bind\n        source: /\n        target: /host\n", ["host_root"]),
        ("    volumes:\n      - /data:/data\n      - [[INSTALL_PATH]]/x:/x\n", []),
        ("    privileged: true\n    volumes:\n      - /:/h\n      - /var/run/docker.sock:/d\n", ["privileged", "docker_socket", "host_root"]),
    ],
)
def test_compose_warnings(extra, expected):
    assert compose_warnings(compose(extra)) == expected


def test_compose_warnings_survive_garbage():
    assert compose_warnings("not: [valid") == []
    assert compose_warnings("") == []
    assert compose_warnings("- a list") == []


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in ("user_packages_hds_folder", "user_packages_available_folder", "user_packages_images_folder", "compose_upload_folder"):
        folder = tmp_path / name
        folder.mkdir()
        monkeypatch.setattr(hds, name, str(folder))

    monkeypatch.setattr(hds, "invalidate_external_apps_cache", lambda: None)
    state = {"installed": False}
    monkeypatch.setattr(hds, "is_app_installed", lambda slug: state["installed"])

    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.add_url_rule("/create", "create", hds.create_hds_from_files, methods=["POST"])
    app.add_url_rule("/register", "register", hds.register_hds_from_files, methods=["POST"])
    app.add_url_rule("/parse", "parse", hds.parse_compose, methods=["POST"])

    return type("Env", (), {"client": app.test_client(), "tmp": tmp_path, "state": state})


def form(slug="demo", yml=None, **extra):
    data = {"slug": slug, "display_name": "Demo", "category": "Media", "type": "Application", "description": "d", "docker_image": "nginx", "author": "me", "version": "latest"}
    data["compose"] = (io.BytesIO((yml or compose(name=slug)).encode()), "docker-compose.yml")
    data["icon"] = (io.BytesIO(PNG), "icon.png")
    data.update(extra)

    return data


def post(env, path, **kwargs):
    return env.client.post(path, data=form(**kwargs), content_type="multipart/form-data")


def test_register_adds_package_without_installing(env):
    response = post(env, "/register")

    assert response.status_code == 200 and response.get_json()["app_slug"] == "demo"
    assert os.path.exists(env.tmp / "user_packages_available_folder" / "demo.yml")
    assert os.path.exists(env.tmp / "user_packages_hds_folder" / "demo.hds")
    assert json.loads((env.tmp / "user_packages_available_folder" / "demo.yml.metadata").read_text())["compose_sha256"]
    assert os.listdir(env.tmp / "compose_upload_folder") == []


def test_register_blocks_installed_app(env):
    env.state["installed"] = True

    response = post(env, "/register")

    assert response.status_code == 409 and response.get_json()["code"] == "APP_INSTALLED"
    assert os.listdir(env.tmp / "user_packages_available_folder") == []


def test_register_asks_before_overwriting_then_overwrites(env):
    assert post(env, "/register").status_code == 200

    asked = post(env, "/register", yml=compose("    privileged: true\n"))
    assert asked.status_code == 409 and asked.get_json()["code"] == "PACKAGE_EXISTS"
    assert "privileged" not in (env.tmp / "user_packages_available_folder" / "demo.yml").read_text()

    done = post(env, "/register", yml=compose("    privileged: true\n"), overwrite="true")
    assert done.status_code == 200
    assert "privileged" in (env.tmp / "user_packages_available_folder" / "demo.yml").read_text()
    assert os.listdir(env.tmp / "user_packages_hds_folder") == ["demo.hds"]


def test_overwrite_also_replaces_an_uploaded_package_with_another_filename(env):
    post(env, "/register")
    os.rename(env.tmp / "user_packages_hds_folder" / "demo.hds", env.tmp / "user_packages_hds_folder" / "Demo Upload.hds")

    assert post(env, "/register", overwrite="true").status_code == 200
    assert os.listdir(env.tmp / "user_packages_hds_folder") == ["demo.hds"]


def test_register_rejects_bad_form(env):
    assert post(env, "/register", slug="Bad Slug").status_code == 400
    assert post(env, "/register", category="Nope").status_code == 400


def test_create_still_downloads_the_package(env):
    response = post(env, "/create")

    assert response.status_code == 200 and response.mimetype == "application/zip"
    assert os.listdir(env.tmp / "user_packages_available_folder") == []


def test_parse_compose_reports_warnings(env):
    response = env.client.post("/parse", data={"compose": (io.BytesIO(compose("    privileged: true\n").encode()), "c.yml")}, content_type="multipart/form-data")

    assert response.get_json()["data"]["warnings"] == ["privileged"]

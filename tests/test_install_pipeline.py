import hashlib
import json
import os
import threading

import pytest
from flask import Flask
from types import SimpleNamespace

from pymodules import hd_InstallPipeline as pipeline
from pymodules import hd_UIAppStoreInstallApp as install_view
from pymodules import hd_UIAppStoreReadSaveYML as config_view

COMPOSE = """services:
  web:
    image: nginx:alpine
    container_name: {name}
    ports:
      - "18080:80"
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    folders = {key: tmp_path / key for key in ("store", "available", "install", "links")}
    for folder in folders.values():
        folder.mkdir()

    monkeypatch.setattr(pipeline, "current_directory", str(tmp_path))
    (tmp_path / "app-store").mkdir()
    monkeypatch.setattr(pipeline, "user_packages_available_folder", str(folders["available"]))
    monkeypatch.setattr(pipeline, "user_packages_install_folder", str(folders["install"]))
    monkeypatch.setattr(pipeline, "compose_upload_folder", str(folders["links"]))
    monkeypatch.setattr(pipeline, "ssl_enabled", lambda: False)
    monkeypatch.setattr(pipeline, "validate_ports", lambda yml, allow_container_name=None: (True, [], []))
    pipeline._staged.clear()
    pipeline._queue.clear()
    pipeline._errors.clear()

    ups = []
    release = threading.Event()
    release.set()

    class FakeCompose:
        def up(self, compose_file, detach=True):
            ups.append(os.path.basename(os.path.dirname(compose_file)))
            release.wait(5)
            return True, ""

    monkeypatch.setattr(pipeline.DockerComposeHelper, "get_instance", staticmethod(lambda: FakeCompose()))

    def bundled(name):
        path = tmp_path / "app-store" / f"{name}.yml"
        path.write_text(COMPOSE.format(name=name))

        return path

    def imported(name, signed=True, tamper=False):
        path = folders["available"] / f"{name}.yml"
        content = COMPOSE.format(name=name)
        path.write_text(content)
        meta = {"name": name}

        if signed:
            meta["compose_sha256"] = hashlib.sha256(content.encode()).hexdigest()

        (folders["available"] / f"{name}.yml.metadata").write_text(json.dumps(meta))

        if tamper:
            path.write_text(content + "    privileged: true\n")

        return path

    return SimpleNamespace(tmp=tmp_path, folders=folders, ups=ups, release=release, bundled=bundled, imported=imported)


def simple():
    return {"ports": ["18080:80"], "volumes": [], "networks": [], "environment": {"A": "1"}}


def test_stage_simple_applies_options(env):
    env.bundled("alpha")

    content_hash = pipeline.stage_config("admin", "alpha", "simple", simple())
    path = pipeline.find_staged("admin", "alpha", content_hash)

    text = open(path).read()
    assert "A: '1'" in text and "restart: unless-stopped" in text
    assert hashlib.sha256(text.encode()).hexdigest()[:16] == content_hash


def test_stage_advanced_uses_given_yaml(env):
    env.bundled("alpha")

    content_hash = pipeline.stage_config("admin", "alpha", "advanced", {"ymlContent": "services:\n  web:\n    image: caddy\n"})

    assert "caddy" in open(pipeline.find_staged("admin", "alpha", content_hash)).read()


def test_unknown_app_and_config_type(env):
    with pytest.raises(pipeline.InstallError) as e:
        pipeline.stage_config("admin", "ghost", "simple", simple())
    assert e.value.status == 404

    env.bundled("alpha")
    with pytest.raises(pipeline.InstallError):
        pipeline.stage_config("admin", "alpha", "wat", {})


def test_port_conflicts_are_reported_with_details(env, monkeypatch):
    env.bundled("alpha")
    monkeypatch.setattr(pipeline, "validate_ports", lambda yml, allow_container_name=None: (False, ["in use"], [18080]))

    with pytest.raises(pipeline.InstallError) as e:
        pipeline.stage_config("admin", "alpha", "simple", simple())

    assert e.value.payload()["messages"] == ["in use"] and e.value.payload()["problematic_ports"] == [18080]


def test_missing_staging_is_a_clear_error(env):
    env.bundled("alpha")

    with pytest.raises(pipeline.InstallError) as e:
        pipeline.enqueue_install("admin", "alpha")
    assert e.value.status == 404 and "Nothing is staged" in e.value.message

    with pytest.raises(pipeline.InstallError) as e:
        pipeline.find_staged("admin", "alpha", "0123456789abcdef")
    assert e.value.status == 404 and "not found" in e.value.message


def test_lookup_is_by_exact_hash_not_first_match(env):
    env.bundled("alpha")
    first = pipeline.stage_config("admin", "alpha", "simple", simple())
    second = pipeline.stage_config("admin", "alpha", "simple", {**simple(), "environment": {"A": "2"}})

    assert first != second
    assert "A: '1'" in open(pipeline.find_staged("admin", "alpha", first)).read()
    assert "A: '2'" in open(pipeline.find_staged("admin", "alpha", second)).read()
    assert pipeline.find_staged("admin", "alpha").endswith(f"{second}/admin_alpha.yml")


def test_tampered_staged_file_is_refused_and_removed(env):
    env.bundled("alpha")
    content_hash = pipeline.stage_config("admin", "alpha", "simple", simple())
    path = pipeline.find_staged("admin", "alpha", content_hash)
    open(path, "a").write("privileged: true\n")

    with pytest.raises(pipeline.InstallError) as e:
        pipeline.find_staged("admin", "alpha", content_hash)

    assert e.value.status == 409 and not os.path.exists(path)


def test_install_copies_link_and_cleans_staging(env):
    env.bundled("alpha")
    content_hash = pipeline.stage_config("admin", "alpha", "simple", simple())

    pipeline.enqueue_install("admin", "alpha", content_hash)

    assert (env.folders["links"] / "alpha.yml").exists()
    assert not (env.folders["install"] / content_hash).exists()
    assert pipeline.installation_status() == {"currently_installing": None, "queue": [], "errors": {}}


def test_failed_up_reports_a_hint_and_still_cleans_up(env, monkeypatch):
    env.bundled("alpha")
    content_hash = pipeline.stage_config("admin", "alpha", "simple", simple())
    monkeypatch.setattr(pipeline.DockerComposeHelper, "get_instance", staticmethod(lambda: SimpleNamespace(up=lambda **kw: (False, "no matching manifest for linux/arm64"))))

    pipeline.enqueue_install("admin", "alpha", content_hash)

    assert "architecture" in pipeline.installation_status()["errors"]["alpha"]
    assert not (env.folders["install"] / content_hash).exists()
    assert not (env.folders["links"] / "alpha.yml").exists()


def test_identical_content_for_two_apps_does_not_cross_cleanup(env):
    env.bundled("alpha")
    env.bundled("beta")
    # same bytes, so the same hash folder
    h1 = pipeline.stage_config("admin", "alpha", "advanced", {"ymlContent": "services:\n  web:\n    image: caddy\n"})
    h2 = pipeline.stage_config("admin", "beta", "advanced", {"ymlContent": "services:\n  web:\n    image: caddy\n"})
    assert h1 == h2

    pipeline.enqueue_install("admin", "alpha", h1)

    assert (env.folders["links"] / "alpha.yml").exists()
    pipeline.enqueue_install("admin", "beta", h2)
    assert (env.folders["links"] / "beta.yml").exists()
    assert not (env.folders["install"] / h1).exists()


def test_concurrent_installs_keep_their_own_entries(env):
    env.release.clear()
    for name in ("alpha", "beta", "gamma"):
        env.bundled(name)
    hashes = {name: pipeline.stage_config("admin", name, "simple", simple()) for name in ("alpha", "beta", "gamma")}

    threads = [threading.Thread(target=pipeline.enqueue_install, args=("admin", name, hashes[name])) for name in hashes]
    threads[0].start()
    for _ in range(100):
        if pipeline.installation_status()["currently_installing"]:
            break
        threading.Event().wait(0.02)

    for t in threads[1:]:
        t.start()
    for t in threads[1:]:
        t.join(2)

    status = pipeline.installation_status()
    assert status["currently_installing"] == "alpha" and sorted(status["queue"]) == ["beta", "gamma"]

    env.release.set()
    threads[0].join(5)

    assert sorted(p.name for p in env.folders["links"].iterdir()) == ["alpha.yml", "beta.yml", "gamma.yml"]
    assert pipeline.installation_status()["currently_installing"] is None
    assert not pipeline._worker_running


def test_queueing_the_same_app_twice_installs_once(env):
    env.release.clear()
    env.bundled("alpha")
    content_hash = pipeline.stage_config("admin", "alpha", "simple", simple())

    first = threading.Thread(target=pipeline.enqueue_install, args=("admin", "alpha", content_hash))
    first.start()
    for _ in range(100):
        if pipeline.installation_status()["currently_installing"]:
            break
        threading.Event().wait(0.02)

    pipeline.enqueue_install("admin", "alpha", content_hash)
    env.release.set()
    first.join(5)

    assert len(env.ups) == 1


def test_signed_package_passes_and_tampered_is_refused(env):
    env.imported("signed")
    env.imported("edited", tamper=True)
    env.imported("unsigned", signed=False)

    assert pipeline.stage_config("admin", "signed", "simple", simple())

    for name in ("edited", "unsigned"):
        with pytest.raises(pipeline.InstallError) as e:
            pipeline.stage_config("admin", name, "simple", simple())
        assert e.value.status == 409 and "signature" in e.value.message


def test_bundled_store_apps_are_not_signature_checked(env):
    env.bundled("alpha")

    assert pipeline.stage_config("admin", "alpha", "simple", simple())


@pytest.fixture
def http(env, monkeypatch):
    user = SimpleNamespace(id="Admin")
    for module in (install_view, config_view):
        monkeypatch.setattr(module, "current_user", user)

    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.add_url_rule("/process", "process", config_view.process_config, methods=["POST"])
    app.add_url_rule("/install", "install", install_view.app_store_install_container, methods=["POST"])
    app.add_url_rule("/status", "status", install_view.get_installation_status)

    return app.test_client()


def test_http_flow_with_and_without_hash(env, http):
    env.bundled("alpha")

    staged = http.post("/process", json={"containerName": "alpha", "configType": "simple", **simple()}).get_json()
    assert staged["success"] and len(staged["contentHash"]) == 16

    assert http.post("/install", json={"containerName": "alpha"}).get_json()["success"]
    assert (env.folders["links"] / "alpha.yml").exists()

    again = http.post("/process", json={"containerName": "alpha", "configType": "simple", **simple()}).get_json()
    assert http.post("/install", json={"containerName": "alpha", "contentHash": again["contentHash"]}).status_code == 200


def test_http_errors(env, http):
    assert http.post("/install", json={}).status_code == 400

    response = http.post("/install", json={"containerName": "alpha"})
    assert response.status_code == 404 and not response.get_json()["success"]

    assert http.post("/process", json={"containerName": "bad/name", "configType": "simple"}).status_code == 400
    assert http.post("/process", json={"containerName": "ghost", "configType": "simple"}).status_code == 404
    assert http.get("/status").get_json() == {"currently_installing": None, "queue": [], "errors": {}}


def test_upload_temp_paths_are_unique():
    from pymodules.hd_HDSPackageManager import _unique_temp_path

    paths = {_unique_temp_path() for _ in range(5)}

    try:
        assert len(paths) == 5 and all(p.endswith(".hds") for p in paths)
    finally:
        for p in paths:
            os.remove(p)


def test_extraction_records_the_compose_signature(tmp_path, monkeypatch):
    from pymodules import hd_HDSPackageManager as hds
    import base64

    for name in ("user_packages_available_folder", "user_packages_images_folder"):
        folder = tmp_path / name
        folder.mkdir()
        monkeypatch.setattr(hds, name, str(folder))

    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
    (tmp_path / "icon.png").write_bytes(png)
    (tmp_path / "compose.yml").write_text(COMPOSE.format(name="demo"))
    metadata = {"category": "Other", "type": "Application", "description": "d", "docker_image": "nginx", "author": "a", "version": "1.0.0"}

    ok, message = hds.create_hds_package("demo", "Demo", str(tmp_path / "demo.hds"), metadata, str(tmp_path / "icon.png"), str(tmp_path / "compose.yml"))
    assert ok, message

    ok, message, manifest = hds.extract_hds_package(str(tmp_path / "demo.hds"), "Demo")
    assert ok, message

    stored = (tmp_path / "user_packages_available_folder" / "demo.yml").read_bytes()
    assert manifest["compose_sha256"] == hashlib.sha256(stored).hexdigest()
    assert json.loads((tmp_path / "user_packages_available_folder" / "demo.yml.metadata").read_text())["compose_sha256"] == manifest["compose_sha256"]

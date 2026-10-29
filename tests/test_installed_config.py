import os

import pytest
import yaml
from flask import Flask

from pymodules import hd_InstalledConfig as ic

COMPOSE = """services:
  web:
    image: nginx:alpine
    container_name: demo
    restart: unless-stopped
    ports:
      - "18080:80"
      - 127.0.0.1:18443:443/tcp
    volumes:
      - /DATA/HomeDock/AppData/demo:/config
      - media:/media:ro
    environment:
      TZ: UTC
      PORT: 80
      ADMIN_PASSWORD: hunter2
    cap_add:
      - NET_ADMIN
    labels:
      keep: me
networks:
  default: {}
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(ic, "compose_upload_folder", str(tmp_path))
    monkeypatch.setattr(ic, "process_devhooks", lambda s, generate_passwords=True: (s.replace("[[INSTALL_PATH]]", "/DATA/HomeDock/AppData"), {}))
    monkeypatch.setattr(ic, "get_config_path", lambda: "/DATA/HomeDock/AppData")
    monkeypatch.setattr(ic, "get_internal_storage_path", lambda: "/DATA/HomeDock/AppFolders")
    monkeypatch.setattr(ic, "validate_ports", lambda yml, allow_container_name=None: (True, None, None))
    monkeypatch.setattr("pymodules.hd_DisksPlusAuth.get_danger_zones", lambda: ("/etc", "/DATA/HomeDock", "/var/lib"))
    monkeypatch.setattr("pymodules.hd_DisksPlusAuth.running_OS", "Linux", raising=False)

    path = tmp_path / "demo.yml"
    path.write_text(COMPOSE)

    return path


def saved(path):
    return yaml.safe_load(path.read_text())["services"]["web"]


def test_read_gives_the_form_shape(env):
    data = ic.read_installed_config("demo")

    assert data["service"] == "web"
    assert data["ports"] == ["18080:80", "127.0.0.1:18443:443/tcp"]
    assert data["volumes"] == ["/DATA/HomeDock/AppData/demo:/config", "media:/media:ro"]
    assert data["environment"] == {"TZ": "UTC", "PORT": "80", "ADMIN_PASSWORD": "hunter2"}
    assert data["capabilities"] == ["NET_ADMIN"] and data["privileged"] is False
    assert data["restartPolicy"] == "unless-stopped" and data["unrepresentable"] == []


def test_read_rejects_bad_or_missing_names(env):
    for name in ("../etc/passwd", "", None, "a/b"):
        with pytest.raises(ic.InstalledConfigError) as e:
            ic.read_installed_config(name)
        assert e.value.status == 400

    with pytest.raises(ic.InstalledConfigError) as e:
        ic.read_installed_config("ghost")
    assert e.value.status == 404


def test_one_changed_field_changes_only_that_field(env):
    before = yaml.safe_load(env.read_text())

    result = ic.update_installed_config("demo", {"restartPolicy": "always"}, apply=True)

    after = yaml.safe_load(env.read_text())
    assert result["changes"] == [{"section": "restartPolicy", "kind": "changed", "before": "unless-stopped", "after": "always"}]
    before["services"]["web"]["restart"] = "always"
    assert after == before


def test_resubmitting_the_same_values_changes_nothing(env):
    original = env.read_text()
    form = {k: v for k, v in ic.read_installed_config("demo").items() if k in ic.SECTIONS}

    result = ic.update_installed_config("demo", form, apply=True)

    assert result["changes"] == [] and not result["applied"] and env.read_text() == original


def test_preview_does_not_write(env):
    original = env.read_text()

    result = ic.update_installed_config("demo", {"privileged": True}, apply=False)

    assert result["changes"][0]["after"] is True and not result["applied"] and env.read_text() == original


def test_ports_add_and_remove(env):
    result = ic.update_installed_config("demo", {"ports": ["18080:80", "19000:9000"]}, apply=True)

    assert {(c["kind"], c["item"]) for c in result["changes"]} == {("removed", "127.0.0.1:18443:443/tcp"), ("added", "19000:9000")}
    assert saved(env)["ports"] == ["18080:80", "19000:9000"]


def test_port_conflicts_are_rejected_with_reasons(env, monkeypatch):
    seen = {}

    def reject(yml, allow_container_name=None):
        seen["ports"] = yaml.safe_load(yml)["services"]["x"]["ports"]
        seen["allow"] = allow_container_name
        return False, [{"key": "Port {port}: Already in use by the system", "params": {"port": 19000}}], [19000]

    monkeypatch.setattr(ic, "validate_ports", reject)

    with pytest.raises(ic.InstalledConfigError) as e:
        ic.update_installed_config("demo", {"ports": ["18080:80", "19000:9000"]}, apply=True)

    assert e.value.payload()["problematic_ports"] == [19000] and e.value.payload()["messages"]
    assert seen == {"ports": ["19000:9000"], "allow": "demo"}
    assert "19000" not in env.read_text()


def test_environment_edit_keeps_untouched_value_types(env):
    result = ic.update_installed_config("demo", {"environment": {"TZ": "Europe/Paris", "PORT": "80", "ADMIN_PASSWORD": "hunter2", "NEW_ONE": "x"}}, apply=True)

    env_after = saved(env)["environment"]
    assert env_after == {"TZ": "Europe/Paris", "PORT": 80, "ADMIN_PASSWORD": "hunter2", "NEW_ONE": "x"}
    assert {(c["kind"], c["item"]) for c in result["changes"]} == {("changed", "TZ"), ("added", "NEW_ONE")}


def test_environment_removal_and_secret_masking(env):
    result = ic.update_installed_config("demo", {"environment": {"TZ": "UTC", "PORT": "80", "ADMIN_PASSWORD": "newpass"}}, apply=False)

    change = result["changes"][0]
    assert change["item"] == "ADMIN_PASSWORD" and change["before"] == ic.MASK and change["after"] == ic.MASK

    removal = ic.update_installed_config("demo", {"environment": {"TZ": "UTC"}}, apply=False)["changes"]
    assert {(c["kind"], c["item"]) for c in removal} == {("removed", "PORT"), ("removed", "ADMIN_PASSWORD")}


@pytest.mark.parametrize("name", ["1BAD", "has space", "A=B", "", "a$b"])
def test_invalid_env_names_are_rejected(env, name):
    with pytest.raises(ic.InstalledConfigError) as e:
        ic.update_installed_config("demo", {"environment": {"TZ": "UTC", "PORT": "80", "ADMIN_PASSWORD": "hunter2", name: "v"}}, apply=True)

    assert "not a valid environment variable name" in e.value.message


def test_list_form_environment_stays_a_list(env):
    env.write_text(COMPOSE.replace("TZ: UTC\n      PORT: 80\n      ADMIN_PASSWORD: hunter2", '- TZ=UTC\n      - PORT=80'))

    assert ic.read_installed_config("demo")["environment"] == {"TZ": "UTC", "PORT": "80"}

    ic.update_installed_config("demo", {"environment": {"TZ": "Asia/Tokyo", "PORT": "80", "X": "1"}}, apply=True)

    assert saved(env)["environment"] == ["TZ=Asia/Tokyo", "PORT=80", "X=1"]


def test_protected_volumes_are_rejected_only_when_new(env):
    with pytest.raises(ic.InstalledConfigError) as e:
        ic.update_installed_config("demo", {"volumes": ["/etc:/host-etc"]}, apply=True)
    assert "protected" in e.value.message

    ic.update_installed_config("demo", {"volumes": ["/DATA/HomeDock/AppData/demo:/config", "media:/media:ro", "/DATA/HomeDock/AppFolders/pics:/pics", "/srv/pics:/p"]}, apply=True)
    assert "/DATA/HomeDock/AppFolders/pics:/pics" in saved(env)["volumes"]


def test_template_placeholders_are_resolved_in_new_entries_only(env):
    ic.update_installed_config("demo", {"volumes": ["/DATA/HomeDock/AppData/demo:/config", "media:/media:ro", "[[INSTALL_PATH]]/extra:/extra"]}, apply=True)

    assert saved(env)["volumes"][-1] == "/DATA/HomeDock/AppData/extra:/extra"


def test_network_change_to_host_clears_ports(env):
    result = ic.update_installed_config("demo", {"networks": ["host"]}, apply=True)

    web = saved(env)
    assert web["network_mode"] == "host" and web["ports"] == [] and "networks" not in web
    assert {c["section"] for c in result["changes"]} == {"networks", "ports"}


def test_network_change_to_custom_declares_it(env):
    ic.update_installed_config("demo", {"networks": ["homedock_network", "backend"]}, apply=True)

    data = yaml.safe_load(env.read_text())
    assert set(data["services"]["web"]["networks"]) == {"homedock_network", "backend"}
    assert data["networks"]["backend"] == {"name": "backend"}


def test_capabilities_and_privileged(env):
    ic.update_installed_config("demo", {"capabilities": [], "privileged": True}, apply=True)
    web = saved(env)
    assert "cap_add" not in web and web["privileged"] is True

    ic.update_installed_config("demo", {"privileged": False}, apply=True)
    assert "privileged" not in saved(env)


def test_labels_container_name_and_other_keys_never_move(env):
    ic.update_installed_config("demo", {"ports": [], "environment": {}, "volumes": []}, apply=True)

    web = saved(env)
    assert web["container_name"] == "demo" and web["labels"] == {"keep": "me"} and web["image"] == "nginx:alpine"


def test_unrepresentable_sections_are_flagged_and_protected(env):
    env.write_text(COMPOSE.replace('- "18080:80"', "- target: 80\n        published: 18080"))

    data = ic.read_installed_config("demo")
    assert "ports" in data["unrepresentable"]

    with pytest.raises(ic.InstalledConfigError):
        ic.update_installed_config("demo", {"ports": ["1:1"]}, apply=True)

    # other sections remain editable
    assert ic.update_installed_config("demo", {"restartPolicy": "always"}, apply=True)["applied"]


def test_anchors_make_everything_read_only(env):
    env.write_text("x-common: &c\n  restart: always\nservices:\n  web:\n    <<: *c\n    image: nginx\n")

    assert ic.read_installed_config("demo")["unrepresentable"] == list(ic.SECTIONS)


def test_group_edits_the_main_service(env):
    env.write_text("services:\n  db:\n    image: pg\n    labels: {HDGroup: g, HDRole: dependency}\n  app:\n    image: a\n    labels: {HDGroup: g, HDRole: main}\n    restart: no\n")

    data = ic.read_installed_config("demo")
    assert data["service"] == "app" and data["dependencies"] == ["db"] and data["hd_group"] == "g"

    ic.update_installed_config("demo", {"restartPolicy": "always"}, apply=True)
    assert yaml.safe_load(env.read_text())["services"]["app"]["restart"] == "always"
    assert "restart" not in yaml.safe_load(env.read_text())["services"]["db"]


def test_http_views(env):
    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.add_url_rule("/get", "get", ic.get_installed_config)
    app.add_url_rule("/set", "set", ic.update_installed_config_view, methods=["POST"])
    client = app.test_client()

    assert client.get("/get?containerName=demo").get_json()["data"]["service"] == "web"
    assert client.get("/get?containerName=ghost").status_code == 404

    preview = client.post("/set", json={"containerName": "demo", "form": {"restartPolicy": "no"}, "apply": False}).get_json()
    assert preview["success"] and len(preview["changes"]) == 1 and not preview["applied"]

    applied = client.post("/set", json={"containerName": "demo", "form": {"restartPolicy": "no"}, "apply": True}).get_json()
    assert applied["applied"] and "restart: 'no'" in applied["ymlContent"].replace('"', "'")

    bad = client.post("/set", json={"containerName": "demo", "form": {"environment": {"1X": "v"}}})
    assert bad.status_code == 400 and "valid environment" in bad.get_json()["message"]

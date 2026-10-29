import copy

from pymodules.hd_RuntimeCompose import NETWORK, build_runtime_compose, parse_port_entry, primary_web_port


def compose(**services):
    return {"services": services}


def test_parse_short_and_long_port_forms():
    assert parse_port_entry("8080:80") == {"target": 80, "published": 8080, "protocol": "tcp"}
    assert parse_port_entry("80") == {"target": 80, "published": None, "protocol": "tcp"}
    assert parse_port_entry("127.0.0.1:8080:80/tcp") == {"target": 80, "published": 8080, "protocol": "tcp"}
    assert parse_port_entry("5353:5353/udp") == {"target": 5353, "published": 5353, "protocol": "udp"}
    assert parse_port_entry(8080) == {"target": 8080, "published": None, "protocol": "tcp"}
    assert parse_port_entry({"target": 80, "published": 8080, "protocol": "tcp"}) == {"target": 80, "published": 8080, "protocol": "tcp"}


def test_parse_ranges_and_variables_are_not_understood():
    assert parse_port_entry("8000-8010:8000-8010") is None
    assert parse_port_entry("${PORT}:80") == {"target": 80, "published": None, "protocol": "tcp"}
    assert parse_port_entry("${PORT}:${INNER}") is None


def test_primary_web_port_is_first_tcp_port():
    services = {"db": {"image": "x"}, "web": {"ports": ["53:53/udp", "8080:80"]}}

    assert primary_web_port(services) == ("web", 80)


def test_primary_web_port_prefers_suggested_port_by_host_or_container_port():
    services = {"web": {"ports": ["8080:80", "9090:9000"]}}

    assert primary_web_port(services, suggested=9090) == ("web", 9000)
    assert primary_web_port(services, suggested=9000) == ("web", 9000)
    assert primary_web_port(services, suggested=1234) == ("web", 80)


def test_primary_web_port_none_without_tcp_ports():
    assert primary_web_port({"web": {"network_mode": "host"}}) is None
    assert primary_web_port({"dns": {"ports": ["53:53/udp"]}}) is None


def test_strips_proxied_port_and_keeps_others():
    original = compose(web={"image": "x", "ports": ["8080:80", "53:53/udp", "2222:22"]})

    result = build_runtime_compose(original, {"web": {80}})

    assert result["services"]["web"]["ports"] == ["53:53/udp", "2222:22"]


def test_removes_ports_key_when_nothing_left():
    result = build_runtime_compose(compose(web={"ports": ["8080:80"]}), {"web": {80}})

    assert "ports" not in result["services"]["web"]


def test_strips_long_form_port():
    original = compose(web={"ports": [{"target": 80, "published": 8080}, {"target": 80, "published": 53, "protocol": "udp"}]})

    result = build_runtime_compose(original, {"web": {80}})

    assert result["services"]["web"]["ports"] == [{"target": 80, "published": 53, "protocol": "udp"}]


def test_service_without_networks_keeps_default_and_joins():
    result = build_runtime_compose(compose(web={"ports": ["8080:80"]}), {"web": {80}})

    assert result["services"]["web"]["networks"] == ["default", NETWORK]
    assert result["networks"][NETWORK] == {"external": True}


def test_service_networks_list_and_dict_forms():
    listed = build_runtime_compose(compose(web={"networks": ["back"]}), {"web": {80}})
    mapped = build_runtime_compose(compose(web={"networks": {"back": {"aliases": ["a"]}}}), {"web": {80}})

    assert listed["services"]["web"]["networks"] == ["back", NETWORK]
    assert mapped["services"]["web"]["networks"] == {"back": {"aliases": ["a"]}, NETWORK: {}}


def test_already_joined_service_is_not_duplicated():
    result = build_runtime_compose(compose(web={"networks": [NETWORK]}), {"web": {80}})

    assert result["services"]["web"]["networks"] == [NETWORK]


def test_existing_non_external_declaration_is_normalized():
    original = {"services": {"web": {"networks": [NETWORK]}}, "networks": {NETWORK: {}, "other": {"driver": "bridge"}}}

    result = build_runtime_compose(original, {})

    assert result["networks"][NETWORK] == {"external": True}
    assert result["networks"]["other"] == {"driver": "bridge"}


def test_services_without_proxied_ports_are_untouched():
    original = compose(web={"ports": ["8080:80"]}, db={"image": "pg", "ports": ["5432:5432"]})

    result = build_runtime_compose(original, {"web": {80}})

    assert result["services"]["db"] == {"image": "pg", "ports": ["5432:5432"]}


def test_host_network_service_is_left_alone():
    original = compose(web={"network_mode": "host"})

    result = build_runtime_compose(original, {"web": {80}})

    assert result == original


def test_no_proxied_ports_and_no_declaration_changes_nothing():
    original = compose(web={"ports": ["8080:80"]})

    assert build_runtime_compose(original, {}) == original


def test_input_is_not_mutated():
    original = compose(web={"ports": ["8080:80"]})
    snapshot = copy.deepcopy(original)

    build_runtime_compose(original, {"web": {80}})

    assert original == snapshot


def _write(tmp_path, text):
    folder = tmp_path / "compose-link"
    folder.mkdir()
    path = folder / "myapp.yml"
    path.write_text(text)

    return str(path)


COMPOSE = "services:\n  web:\n    image: x\n    container_name: myapp\n    ports:\n      - '8080:80'\n      - '53:53/udp'\n"


def test_runtime_file_in_container_mode_unpublishes_and_keeps_project(tmp_path, monkeypatch):
    import os

    import yaml

    from pymodules import hd_RuntimeCompose as module

    monkeypatch.setattr(module, "is_docker", True)
    path = _write(tmp_path, COMPOSE)

    with module.runtime_compose_file(path) as (run_file, project, project_dir):
        runtime = yaml.safe_load(open(run_file))

        assert run_file != path
        assert project == "compose-link"
        assert project_dir == os.path.dirname(path)
        assert runtime["services"]["web"]["ports"] == ["53:53/udp"]
        assert runtime["services"]["web"]["networks"] == ["default", NETWORK]
        assert runtime["networks"][NETWORK] == {"external": True}

    assert not os.path.exists(run_file)
    assert open(path).read() == COMPOSE


def test_runtime_file_falls_back_to_users_file_on_bad_yaml(tmp_path, monkeypatch):
    from pymodules import hd_RuntimeCompose as module

    monkeypatch.setattr(module, "is_docker", True)
    path = _write(tmp_path, "services: [unclosed")

    with module.runtime_compose_file(path) as (run_file, _, _):
        assert run_file == path


def test_loopback_mode_publishes_only_on_localhost_and_skips_the_network():
    original = compose(web={"ports": ["8080:80", "53:53/udp"]})

    result = build_runtime_compose(original, {"web": {80}}, loopback=True)

    assert result["services"]["web"]["ports"] == ["53:53/udp", "127.0.0.1::80"]
    assert "networks" not in result["services"]["web"]
    assert "networks" not in result


def test_loopback_mode_adds_a_port_the_file_only_exposes():
    result = build_runtime_compose(compose(web={"image": "x"}), {"web": {3000}}, loopback=True)

    assert result["services"]["web"]["ports"] == ["127.0.0.1::3000"]


def test_loopback_mode_collapses_duplicate_entries_for_one_port():
    original = compose(web={"ports": ["8080:80", {"target": 80, "published": 9090}]})

    result = build_runtime_compose(original, {"web": {80}}, loopback=True)

    assert result["services"]["web"]["ports"] == ["127.0.0.1::80"]


def test_loopback_mode_leaves_host_network_services_alone():
    original = compose(web={"network_mode": "host"})

    assert build_runtime_compose(original, {"web": {80}}, loopback=True) == original


def test_runtime_file_outside_docker_publishes_on_loopback(tmp_path, monkeypatch):
    import yaml

    from pymodules import hd_RuntimeCompose as module

    monkeypatch.setattr(module, "is_docker", False)
    path = _write(tmp_path, COMPOSE)

    with module.runtime_compose_file(path) as (run_file, project, _):
        assert run_file != path
        assert yaml.safe_load(open(run_file))["services"]["web"]["ports"] == ["53:53/udp", "127.0.0.1::80"]

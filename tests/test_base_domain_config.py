import pymodules.hd_ComposeDevHooks as devhooks
import pymodules.hd_FunctionsConfig as functions_config


def test_fresh_config_has_empty_base_domain(tmp_path, monkeypatch):
    monkeypatch.setattr(functions_config, "current_directory", str(tmp_path))

    functions_config.check_and_generate_config()
    config = functions_config.read_config()

    assert config["base_domain"] == ""
    assert "dynamic_dns" not in config
    assert "dynamic_dns_sync" in config


def test_hd_dyn_dns_alias_resolves_to_base_domain(monkeypatch):
    monkeypatch.setattr(devhooks, "read_config", lambda: {"base_domain": "home.example.com", "user_name": "User"})

    yml, values = devhooks.process_devhooks("host: [[HD_DYN_DNS]]")

    assert yml == "host: home.example.com"
    assert values["dynamic_dns"] == "home.example.com"

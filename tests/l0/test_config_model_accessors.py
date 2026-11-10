"""模型配置读取的集中入口（SPEC-009 / SPEC-022 AC-4）。"""

from __future__ import annotations

import json

import pytest

from src.utils import config


@pytest.fixture
def model_config(monkeypatch):
    def fake_get_model_config():
        return {
            "main": {
                "m-a": {"base_url": "u", "max_token": 1234},
                "m-b": {"max_token": "not-a-number"},
            },
            "task": {},
        }

    monkeypatch.setattr(config, "get_model_config", fake_get_model_config)
    return fake_get_model_config


def test_get_main_model_config_by_name(model_config):
    assert config.get_main_model_config("m-a") == {
        "base_url": "u",
        "max_token": 1234,
    }


def test_get_main_model_config_defaults_to_first_entry(model_config):
    assert config.get_main_model_config()["base_url"] == "u"


def test_get_main_model_config_handles_missing_and_bad_shapes(monkeypatch):
    monkeypatch.setattr(config, "get_model_config", lambda: {"main": "oops"})
    assert config.get_main_model_config("x") == {}

    monkeypatch.setattr(config, "get_model_config", lambda: {})
    assert config.get_main_model_config() == {}


def test_get_model_max_token_reads_int_and_falls_back(model_config):
    assert config.get_model_max_token("m-a") == 1234
    assert config.get_model_max_token("m-b") == 500000
    assert config.get_model_max_token("missing") == 500000
    assert config.get_model_max_token("missing", default=9) == 9


def test_get_agent_model_uses_first_key_or_default(monkeypatch):
    """SPEC-022 AC-4：main 结构异常时回落到内置模型名。"""
    monkeypatch.setattr(
        config, "get_model_config", lambda: {"main": {"m-a": {}, "m-b": {}}}
    )
    assert config.get_agent_model() == "m-a"

    for payload in ({}, {"main": {}}, {"main": []}, {"main": "oops"}):
        monkeypatch.setattr(config, "get_model_config", lambda p=payload: p)
        assert config.get_agent_model() == "openai:deepseek-v4-flash"


def test_get_model_max_token_rejects_non_numeric_values(monkeypatch):
    """SPEC-022 AC-4：None / 小数串等无法转 int 时回落默认值。"""
    for value in (None, "12.5", [1]):
        monkeypatch.setattr(
            config, "get_main_model_config", lambda name, v=value: {"max_token": v}
        )
        assert config.get_model_max_token() == 500000


def test_read_json_if_exists_handles_missing_valid_and_broken(tmp_path, capsys):
    """SPEC-022 AC-4：配置不存在返回空 dict，损坏时告警后返回空 dict。"""
    missing = tmp_path / "missing.json"
    assert config._read_json_if_exists(str(missing)) == {}

    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps({"ok": 1}), encoding="utf-8")
    assert config._read_json_if_exists(str(valid)) == {"ok": 1}

    broken = tmp_path / "broken.json"
    broken.write_text("{not-json", encoding="utf-8")
    assert config._read_json_if_exists(str(broken)) == {}
    assert "加载 JSON 文件失败" in capsys.readouterr().out


def test_config_getters_return_empty_when_files_missing(tmp_path, monkeypatch):
    """SPEC-022 AC-4：各配置文件缺失时统一返回空 dict。"""
    for attr in (
        "MODEL_CONFIG_PATH",
        "SENSOR_CONFIG_PATH",
        "FILE_CONFIG_PATH",
        "MCP_CONFIG_PATH",
    ):
        monkeypatch.setattr(config, attr, str(tmp_path / f"{attr}.json"))

    assert config.get_model_config() == {}
    assert config.get_sensor_config() == {}
    assert config.get_file_config() == {}
    assert config.get_mcp_config() == {}


def test_read_settings_and_data_root_fallbacks(tmp_path, monkeypatch):
    """SPEC-022 AC-4：settings 缺失/损坏/相对路径均回落，绝对路径去空白。"""
    monkeypatch.setattr(config, "PURRCAT_DIR", str(tmp_path))
    settings = tmp_path / "settings.json"

    assert config._read_settings() == {}
    assert config._get_data_root() == str(tmp_path)
    assert config.is_data_root_configured() is False

    settings.write_text("{broken", encoding="utf-8")
    assert config._read_settings() == {}
    assert config._get_data_root() == str(tmp_path)

    settings.write_text(json.dumps({"data_root": "relative/path"}), encoding="utf-8")
    assert config._get_data_root() == str(tmp_path)
    assert config.is_data_root_configured() is True

    absolute = tmp_path / "large-data"
    settings.write_text(json.dumps({"data_root": f"  {absolute}  "}), encoding="utf-8")
    assert config._get_data_root() == str(absolute)


def test_read_settings_rejects_non_object_json(tmp_path, monkeypatch):
    """SPEC-022 AC-4：settings.json 是数组/标量时按缺省处理。"""
    monkeypatch.setattr(config, "PURRCAT_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text("[]", encoding="utf-8")

    assert config._read_settings() == {}
    assert config.is_data_root_configured() is False

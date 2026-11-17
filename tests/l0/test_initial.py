"""首启默认配置模板与幂等生成（SPEC-015）。"""

from __future__ import annotations

import json
from pathlib import Path

from src.utils import initial, initial_templates


def test_default_paradigm_template_is_unchanged():
    text = initial_templates.DEFAULT_PARADIGM_YAML

    assert 'name: "default"' in text
    assert "loop_end_max_retry: 3" in text
    assert "@RULES" in text and "@SOUL" in text


def test_model_config_covers_main_task_and_vision():
    config = initial_templates.model_config_dict()

    assert set(config) == {"main", "task", "vision"}
    assert config["main"]["openai:deepseek-flash"]["base_url"] == (
        "https://api.deepseek.com"
    )
    assert config["vision"]["openai:deepseek-flash"]["base_url"] == (
        "https://api.deepseek.com"
    )
    assert "vision" not in config["vision"]["openai:deepseek-flash"]


def test_text_templates_are_valid_json():
    assert json.loads(initial_templates.HEARTBEAT_CONFIG_TEMPLATE) == {
        "interval": 1800,
        "active": False,
    }
    assert initial_templates.MEMORY_MD_TEMPLATE.startswith("当前阶段")


def test_generate_all_configs_is_idempotent(tmp_path, monkeypatch):
    root = tmp_path / "purrcat"
    core = root / "core"
    monkeypatch.setattr(initial, "PURRCAT_DIR", str(root))
    monkeypatch.setattr(initial, "AGENT_CORE_DIR", str(core))
    monkeypatch.setattr(initial, "MODEL_CONFIG_PATH", str(root / "model.json"))
    monkeypatch.setattr(initial, "SENSOR_CONFIG_PATH", str(root / "sensor.json"))
    monkeypatch.setattr(initial, "FILE_CONFIG_PATH", str(root / "file.json"))
    monkeypatch.setattr(initial, "MCP_CONFIG_PATH", str(root / "mcp.json"))
    monkeypatch.setattr(initial, "HEARTBEAT_FILE", str(core / "heartbeat.json"))
    monkeypatch.setattr(initial, "SOUL_MD_PATH", str(core / "SOUL.md"))
    monkeypatch.setattr(initial, "SKILL_DIR", str(root / "skills"))
    monkeypatch.setattr(initial, "BUILTIN_SKILLS_DIR", str(tmp_path / "no-builtin"))
    monkeypatch.setattr(initial, "get_acp_token", lambda: "token")
    monkeypatch.setattr(initial, "deploy_acp_relay", lambda: True)

    initial._generate_all_configs()
    assert (root / "model.json").exists()
    assert (core / "MEMORY.md").exists()
    assert (core / "SOUL.md").exists()

    (root / "model.json").write_text('{"custom": true}', encoding="utf-8")
    initial._generate_all_configs()

    assert json.loads((root / "model.json").read_text(encoding="utf-8")) == {
        "custom": True
    }


def test_repo_ships_builtin_skills():
    """内置技能源随仓库分发，打包时由 collect_all('src') 带进 _internal。"""
    for name in ("purrcat-note", "purrcat-genui"):
        assert (Path(initial.BUILTIN_SKILLS_DIR) / name / "SKILL.md").is_file()


def test_sync_builtin_skills_copies_missing_and_keeps_user_copy(tmp_path, monkeypatch):
    source = tmp_path / "builtin"
    (source / "purrcat-note").mkdir(parents=True)
    (source / "purrcat-note" / "SKILL.md").write_text(
        "name: purrcat-note", encoding="utf-8"
    )
    target = tmp_path / "skills"
    monkeypatch.setattr(initial, "BUILTIN_SKILLS_DIR", str(source))
    monkeypatch.setattr(initial, "SKILL_DIR", str(target))

    assert initial.sync_builtin_skills() == ["purrcat-note"]
    copied = target / "purrcat-note" / "SKILL.md"
    assert copied.read_text(encoding="utf-8") == "name: purrcat-note"

    copied.write_text("user edited", encoding="utf-8")
    assert initial.sync_builtin_skills() == []
    assert copied.read_text(encoding="utf-8") == "user edited"

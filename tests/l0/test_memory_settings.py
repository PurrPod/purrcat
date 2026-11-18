"""记忆用户配置的默认值、校验与原子保存（记忆设置页）。"""

from __future__ import annotations

import json
import os

import pytest

from src.memory import settings


def test_defaults_when_file_missing(tmp_path):
    missing = str(tmp_path / "memory.json")

    assert settings.get_memory_settings(path=missing) == settings.DEFAULTS


def test_get_fills_missing_and_ignores_broken_fields(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text(
        json.dumps({"decay_half_life_days": "abc"}),
        encoding="utf-8",
    )

    loaded = settings.get_memory_settings(path=str(path))

    assert loaded["decay_half_life_days"] == settings.DEFAULTS["decay_half_life_days"]
    assert loaded["event_retention_days"] == settings.DEFAULTS["event_retention_days"]


def test_validate_coerces_strings_and_rounds_floats():
    result = settings.validate_memory_settings(
        {"event_retention_days": "30", "decay_half_life_days": "45.123456"}
    )

    assert result == {
        "event_retention_days": 30,
        "decay_half_life_days": 45.1235,
    }


def test_legacy_fields_are_dropped():
    """旧版 memory.json 的 search_top_k / min_experience_score 不再暴露。"""
    result = settings.validate_memory_settings(
        {"event_retention_days": 30, "search_top_k": 8, "min_experience_score": 0.5}
    )

    assert "search_top_k" not in result
    assert "min_experience_score" not in result


@pytest.mark.parametrize(
    "payload",
    [
        {"event_retention_days": -1},
        {"event_retention_days": 1.5},
        {"decay_half_life_days": 0},
        {"decay_half_life_days": 3651},
        {"event_retention_days": "many"},
        {"decay_half_life_days": float("nan")},
    ],
)
def test_validate_rejects_invalid_values(payload):
    with pytest.raises(ValueError):
        settings.validate_memory_settings(payload)


def test_validate_rejects_non_object():
    with pytest.raises(ValueError):
        settings.validate_memory_settings([1, 2, 3])


def test_save_writes_normalized_json_atomically(tmp_path):
    path = tmp_path / "nested" / "memory.json"

    saved = settings.save_memory_settings({"event_retention_days": "7"}, path=str(path))

    assert saved["event_retention_days"] == 7
    assert json.loads(path.read_text(encoding="utf-8")) == {**saved, "_version": 1}
    assert not os.path.exists(str(path) + ".tmp")


def test_save_invalid_value_leaves_file_untouched(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text(json.dumps({"event_retention_days": 30}), encoding="utf-8")

    with pytest.raises(ValueError):
        settings.save_memory_settings({"event_retention_days": -1}, path=str(path))

    assert json.loads(path.read_text(encoding="utf-8")) == {"event_retention_days": 30}


def test_save_preserves_runtime_state(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text(
        json.dumps(
            {
                "event_retention_days": 30,
                "_version": 1,
                "_state": {"last_decay_at": "2026-01-01T00:00:00"},
            }
        ),
        encoding="utf-8",
    )

    settings.save_memory_settings({"event_retention_days": 7}, path=str(path))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["event_retention_days"] == 7
    assert payload["_state"] == {"last_decay_at": "2026-01-01T00:00:00"}


def test_update_state_keeps_user_settings(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text(
        json.dumps(
            {"event_retention_days": 30, "decay_half_life_days": 20, "_version": 1}
        ),
        encoding="utf-8",
    )

    settings.update_memory_state(
        {"last_decay_at": "2026-01-02T00:00:00"}, path=str(path)
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["event_retention_days"] == 30
    assert payload["decay_half_life_days"] == 20
    assert payload["_state"] == {"last_decay_at": "2026-01-02T00:00:00"}
    assert payload["_version"] == 1

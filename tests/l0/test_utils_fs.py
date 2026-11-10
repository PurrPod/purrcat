"""utils 共用的 JSON / 文本读写与目录查找（SPEC-015）。"""

from __future__ import annotations

import json

import pytest

from src.utils import _fs


def test_write_json_creates_parent_and_keeps_unicode(tmp_path):
    target = tmp_path / "nested" / "settings.json"

    _fs.write_json(str(target), {"name": "猫"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"name": "猫"}
    assert "\n  " in target.read_text(encoding="utf-8")


def test_write_text_creates_parent(tmp_path):
    target = tmp_path / "core" / "MEMORY.md"

    _fs.write_text(str(target), "# 记忆")

    assert target.read_text(encoding="utf-8") == "# 记忆"


def test_read_json_round_trip_and_fallbacks(tmp_path):
    target = tmp_path / "settings.json"
    _fs.write_json(str(target), {"name": "猫"})

    assert _fs.read_json(str(target)) == {"name": "猫"}
    assert _fs.read_json(str(tmp_path / "missing.json"), {"d": 1}) == {"d": 1}

    target.write_text("{broken", encoding="utf-8")
    assert _fs.read_json(str(target), []) == []
    assert _fs.read_json(str(target)) is None


def test_api_common_read_json_file_delegates(tmp_path):
    from src.server.api.common import read_json_file

    target = tmp_path / "plugin.json"
    target.write_text('{"id": "x"}', encoding="utf-8")

    assert read_json_file(str(target)) == {"id": "x"}
    assert read_json_file(str(tmp_path / "missing.json"), {}) == {}


def test_read_jsonl_skips_blank_and_broken_lines(tmp_path):
    target = tmp_path / "log.jsonl"
    target.write_text('{"a": 1}\n\n{broken\n{"b": 2}\n', encoding="utf-8")

    assert _fs.read_jsonl(str(target)) == [{"a": 1}, {"b": 2}]

    broken: list[str] = []
    assert _fs.read_jsonl(str(target), on_error=broken.append) == [
        {"a": 1},
        {"b": 2},
    ]
    assert broken == ["{broken"]


def test_read_jsonl_propagates_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        _fs.read_jsonl(str(tmp_path / "missing.jsonl"))


def test_write_json_atomic_replaces_and_cleans_temp(tmp_path):
    target = tmp_path / "state.json"

    _fs.write_json_atomic(str(target), {"n": 1})
    _fs.write_json_atomic(str(target), {"n": 2, "猫": True})

    assert json.loads(target.read_text(encoding="utf-8")) == {"n": 2, "猫": True}
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_write_json_atomic_supports_compact_output(tmp_path):
    target = tmp_path / "deps.json"

    _fs.write_json_atomic(str(target), {"fingerprint": "abc"}, indent=None)

    assert target.read_text(encoding="utf-8") == '{"fingerprint": "abc"}'


def test_find_child_dir_by_token_returns_first_match(tmp_path):
    (tmp_path / "task_alpha").mkdir()
    (tmp_path / "task_beta").mkdir()

    assert _fs.find_child_dir_by_token(str(tmp_path), "alpha") == str(
        tmp_path / "task_alpha"
    )
    assert _fs.find_child_dir_by_token(str(tmp_path), "missing") is None
    assert _fs.find_child_dir_by_token(str(tmp_path / "nope"), "alpha") is None

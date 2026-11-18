"""更换数据根目录：整目录复制到空目标，旧数据保留，沙盒重建。"""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

from src.server.api import config_services


@pytest.fixture
def env(tmp_path, monkeypatch):
    old = tmp_path / "old_root"
    (old / "agent_vm").mkdir(parents=True)
    (old / "agent_vm" / "note.txt").write_text("hello", encoding="utf-8")
    (old / "embedding").mkdir()
    (old / "embedding" / "model.bin").write_bytes(b"model")

    saved = {}
    monkeypatch.setattr(config_services, "DATA_ROOT", str(old))
    monkeypatch.setattr(
        config_services,
        "save_global_setting",
        lambda key, value: saved.update({key: value}) is None,
    )
    destroyed = {"count": 0}
    monkeypatch.setattr(
        config_services,
        "_destroy_sandbox_container",
        lambda: destroyed.update(count=destroyed["count"] + 1),
    )
    return old, saved, destroyed


def test_copies_whole_root_into_empty_destination(env, tmp_path):
    old, saved, destroyed = env
    new = tmp_path / "new_root"

    result = config_services.change_data_root({"data_root": str(new)})

    assert result["copied_files"] == 2
    assert (new / "agent_vm" / "note.txt").read_text(encoding="utf-8") == "hello"
    assert (new / "embedding" / "model.bin").read_bytes() == b"model"
    # 旧数据保留（copy 而非 move）
    assert (old / "agent_vm" / "note.txt").exists()
    assert saved["data_root"] == str(new)
    assert destroyed["count"] == 1


def test_existing_empty_directory_is_accepted(env, tmp_path):
    _, _, _ = env
    new = tmp_path / "new_root"
    new.mkdir()

    result = config_services.change_data_root({"data_root": str(new)})

    assert result["status"] == "ok"
    assert (new / "agent_vm" / "note.txt").exists()


def test_non_empty_destination_is_rejected(env, tmp_path):
    _, saved, destroyed = env
    new = tmp_path / "new_root"
    new.mkdir()
    (new / "occupied.txt").write_text("x", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        config_services.change_data_root({"data_root": str(new)})

    assert exc.value.status_code == 409
    assert "为空" in exc.value.detail
    assert "data_root" not in saved
    assert destroyed["count"] == 0


def test_same_destination_is_rejected(env):
    old, visited, _ = env

    with pytest.raises(HTTPException) as exc:
        config_services.change_data_root({"data_root": str(old)})

    assert exc.value.status_code == 400
    assert "data_root" not in visited


def test_destination_inside_old_root_is_rejected(env):
    old, _, _ = env

    with pytest.raises(HTTPException) as exc:
        config_services.change_data_root({"data_root": os.path.join(str(old), "inner")})

    assert exc.value.status_code == 400

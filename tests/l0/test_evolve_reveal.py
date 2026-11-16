"""沙盒工作区目录「查看文件」服务函数（SPEC-031）。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.server.api import evolve_service


def test_resolve_workplace_dir_joins_type_workplace(tmp_path, monkeypatch):
    monkeypatch.setattr(evolve_service, "AGENT_VM_DIR", str(tmp_path))
    path = evolve_service.resolve_workplace_dir("skill", "wp-1")
    assert path == str(tmp_path / "skill_workplace" / "wp-1")


@pytest.mark.parametrize("bad", ["", "../x", "a/b", "a\\b"])
def test_resolve_workplace_dir_rejects_unsafe_id(bad):
    with pytest.raises(HTTPException) as err:
        evolve_service.resolve_workplace_dir("skill", bad)
    assert err.value.status_code == 400


def test_reveal_workplace_opens_dir_and_returns_path(tmp_path, monkeypatch):
    monkeypatch.setattr(evolve_service, "AGENT_VM_DIR", str(tmp_path))
    target = tmp_path / "sensor_workplace" / "wp-2"
    target.mkdir(parents=True)
    opened: list[str] = []
    monkeypatch.setattr(evolve_service, "_open_in_file_manager", opened.append)

    result = evolve_service.reveal_workplace("sensor", "wp-2")

    assert result == {"ok": True, "path": str(target)}
    assert opened == [str(target)]


def test_reveal_workplace_missing_dir_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(evolve_service, "AGENT_VM_DIR", str(tmp_path))
    with pytest.raises(HTTPException) as err:
        evolve_service.reveal_workplace("skill", "nope")
    assert err.value.status_code == 404
    assert "不存在" in err.value.detail

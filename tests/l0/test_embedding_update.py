"""嵌入模型更新任务（SPEC-043）。"""

from __future__ import annotations

import json

import pytest

from src.memory import embedding_update


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(
        embedding_update, "MARKER_PATH", str(tmp_path / "embedding_update.json")
    )
    embedding_update._running.clear()
    with embedding_update._lock:
        embedding_update._state.update(
            state="idle",
            phase="",
            message="",
            error="",
            report=None,
            started_at=None,
            finished_at=None,
        )
    yield
    embedding_update._running.clear()


def _quiet(*_args):
    return None


def test_run_update_installs_model_then_rebuilds(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(embedding_update, "model_dir_state", lambda _dir: "outdated")
    monkeypatch.setattr(
        embedding_update,
        "install_embedding_model",
        lambda log: calls.append("install") or {},
    )
    monkeypatch.setattr(
        embedding_update,
        "_release_runtime_embedder",
        lambda log: calls.append("release"),
    )
    monkeypatch.setattr(
        embedding_update,
        "rebuild_vector_index",
        lambda log: {"counts": {"events": 3}},
    )

    status = embedding_update.run_update(log=_quiet)

    assert calls == ["release", "install", "release"]
    assert status["state"] == "done"
    assert status["phase"] == "done"
    assert status["report"] == {"counts": {"events": 3}}
    marker = json.loads((tmp_path / "embedding_update.json").read_text("utf-8"))
    assert marker["state"] == "done"


def test_run_update_skips_download_when_model_is_current(monkeypatch):
    monkeypatch.setattr(embedding_update, "model_dir_state", lambda _dir: "current")

    def _fail(*_args, **_kwargs):
        raise AssertionError("模型已是最新时不应重新下载")

    monkeypatch.setattr(embedding_update, "install_embedding_model", _fail)
    rebuilt = []
    monkeypatch.setattr(
        embedding_update,
        "rebuild_vector_index",
        lambda log: rebuilt.append(True) or {"counts": {}},
    )

    status = embedding_update.run_update(log=_quiet)

    assert rebuilt == [True]
    assert status["state"] == "done"


def test_run_update_records_error_and_keeps_retryable_state(monkeypatch, tmp_path):
    monkeypatch.setattr(embedding_update, "model_dir_state", lambda _dir: "current")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("向量库重建失败")

    monkeypatch.setattr(embedding_update, "rebuild_vector_index", _boom)

    status = embedding_update.run_update(log=_quiet)

    assert status["state"] == "error"
    assert "向量库重建失败" in status["error"]
    marker = json.loads((tmp_path / "embedding_update.json").read_text("utf-8"))
    assert marker["state"] == "error"


def test_start_update_rejects_concurrent_run(monkeypatch):
    embedding_update._running.set()
    started = []

    monkeypatch.setattr(
        embedding_update,
        "install_embedding_model",
        lambda log: started.append(True),
    )

    result = embedding_update.start_update()

    assert result["started"] is False
    assert started == []


def test_interrupted_marker_is_reported_after_restart(monkeypatch, tmp_path):
    (tmp_path / "embedding_update.json").write_text(
        json.dumps({"state": "running", "phase": "rebuilding"}), encoding="utf-8"
    )

    status = embedding_update.update_status()

    assert status["interrupted"] is True


def test_running_job_is_not_reported_as_interrupted(monkeypatch, tmp_path):
    (tmp_path / "embedding_update.json").write_text(
        json.dumps({"state": "running", "phase": "rebuilding"}), encoding="utf-8"
    )
    embedding_update._running.set()
    with embedding_update._lock:
        embedding_update._state.update(state="running", phase="rebuilding")

    status = embedding_update.update_status()

    assert status["interrupted"] is False

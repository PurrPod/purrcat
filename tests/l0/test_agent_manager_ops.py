"""AgentManager 会话切换原子操作与会话删除（SPEC-006）。"""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

from src.agent import session_store
from src.agent.manager import AgentManager
from src.agent.session_store import SessionStore


def test_wait_until_idle_returns_immediately_when_idle():
    manager = object.__new__(AgentManager)
    manager._agent = SimpleNamespace(state="idle")

    manager._wait_until_idle("waiting")


def test_wait_until_idle_waits_for_idle(monkeypatch):
    manager = object.__new__(AgentManager)
    manager._agent = SimpleNamespace(state="handling")
    slept = []

    def fake_sleep(_):
        slept.append(1)
        manager._agent.state = "idle"

    monkeypatch.setattr("src.agent.manager.time.sleep", fake_sleep)

    manager._wait_until_idle("waiting")

    assert slept


def test_adopt_session_switches_all_fields_under_lock():
    manager = object.__new__(AgentManager)
    lock = threading.RLock()
    manager._agent = SimpleNamespace(
        session_id="old",
        current_history=[],
        window_token=1,
        consumed_tokens=2,
        _history_lock=lock,
    )
    history = [{"role": "system", "content": "s"}]

    manager._adopt_session("new", history, 10, 20)

    assert manager._agent.session_id == "new"
    assert manager._agent.current_history is history
    assert manager._agent.window_token == 10
    assert manager._agent.consumed_tokens == 20


def test_session_store_delete_removes_dir_and_index(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "session_x"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text("{}", encoding="utf-8")
    index_path = sessions_dir / "index.json"
    index_path.write_text(
        json.dumps({"session_x": {"alias": "x"}, "session_y": {"alias": "y"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(session_store, "SESSIONS_DIR", str(sessions_dir))
    monkeypatch.setattr(session_store, "SESSION_INDEX_PATH", str(index_path))

    SessionStore.delete_session("session_x")

    assert not session_dir.exists()
    assert json.loads(index_path.read_text(encoding="utf-8")) == {
        "session_y": {"alias": "y"}
    }


def test_session_store_delete_is_idempotent_for_missing_session(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    index_path = sessions_dir / "index.json"
    index_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(session_store, "SESSIONS_DIR", str(sessions_dir))
    monkeypatch.setattr(session_store, "SESSION_INDEX_PATH", str(index_path))

    SessionStore.delete_session("session_missing")

    assert json.loads(index_path.read_text(encoding="utf-8")) == {}


def _make_notify_manager(history):
    manager = object.__new__(AgentManager)
    manager._last_saved_sig = None
    manager._agent = SimpleNamespace(
        get_history=lambda: history,
        session_id="session_a",
        window_token=1,
        consumed_tokens=2,
    )
    return manager


def test_notify_save_skips_write_when_history_unchanged(monkeypatch):
    """切会话/启动时内容没变就不落盘，避免刷新旧会话的 updated_at 把它顶到列表最前。"""
    calls = []
    monkeypatch.setattr(
        "src.agent.manager.SessionStore.save_session",
        lambda *a, **kw: calls.append((a, kw)),
    )
    manager = _make_notify_manager([{"role": "user", "content": "hi"}])

    manager._notify_save()
    manager._notify_save()

    assert len(calls) == 1


def test_notify_save_writes_again_after_history_changes(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "src.agent.manager.SessionStore.save_session",
        lambda *a, **kw: calls.append((a, kw)),
    )
    history = [{"role": "user", "content": "hi"}]
    manager = _make_notify_manager(history)

    manager._notify_save()
    history.append({"role": "assistant", "content": "ok"})
    manager._notify_save()
    # 长度不变但最后一条内容变化（流式覆盖）同样要落盘
    history[-1]["content"] = "ok!"
    manager._notify_save()

    assert len(calls) == 3

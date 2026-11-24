"""新会话草稿态：draft 标识、延迟系统提示与启动对账（SPEC-044）。"""

from __future__ import annotations

import json

import pytest

from src.agent import project_store
from src.agent import session_store as store_mod
from src.agent.agent import Agent
from src.agent.session_store import SessionStore


class _NoopTracker:
    def add(self, message):
        pass


class _Hooks:
    def __init__(self, prompt="系统提示"):
        self.prompt = prompt
        self.calls = []

    def execute(self, stage_name, **kwargs):
        self.calls.append(stage_name)
        if stage_name == "on_build_system_prompt":
            return [{"success": True, "inject_prompt": self.prompt}]
        return []

    def get_state(self):
        return {}

    def load_state(self, state):
        pass


class _NoopModel:
    vision = False

    def bind_task(self, task_id, task_name=None):
        return self

    def unbind(self):
        pass

    def chat(self, *args, **kwargs):
        raise AssertionError("草稿构建流程不应调用模型")


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    root.mkdir()
    index_path = root / "index.json"
    index_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(store_mod, "SESSIONS_DIR", str(root))
    monkeypatch.setattr(store_mod, "SESSION_INDEX_PATH", str(index_path))
    return root, index_path


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _draft_agent(hooks=None):
    return Agent(
        session_id="session_draft",
        initial_history=[],
        name="test-model",
        save_callback=lambda: None,
        model=_NoopModel(),
        hook_handler=hooks or _Hooks(),
        tracker=_NoopTracker(),
        memo=[],
        defer_system_prompt=True,
    )


# ---- AC-1：draft 字段读写语义 ----


def test_save_session_draft_flag_write_remove_and_preserve(sessions):
    sessions
    SessionStore.save_session("session_a", [], alias="新建会话", draft=True)

    root, index_path = sessions
    assert _read_json(root / "session_a" / "meta.json")["draft"] is True
    assert _read_json(index_path)["session_a"]["draft"] is True
    assert SessionStore.is_session_draft("session_a") is True

    # checkpoint 不传 draft：必须保留，不能误清
    SessionStore.save_session("session_a", [], window_token=3)
    assert _read_json(root / "session_a" / "meta.json")["draft"] is True
    assert _read_json(index_path)["session_a"]["draft"] is True

    # 显式 False：清理标记
    SessionStore.save_session(
        "session_a", [{"role": "system", "content": "s"}], draft=False
    )
    assert "draft" not in _read_json(root / "session_a" / "meta.json")
    assert "draft" not in _read_json(index_path)["session_a"]
    assert SessionStore.is_session_draft("session_a") is False


def test_set_session_draft_writes_meta_and_index(sessions):
    sessions
    SessionStore.save_session("session_a", [], alias="甲")

    assert SessionStore.is_session_draft("session_a") is False

    SessionStore.set_session_draft("session_a", True)
    root, index_path = sessions
    assert _read_json(root / "session_a" / "meta.json")["draft"] is True
    assert _read_json(index_path)["session_a"]["draft"] is True

    SessionStore.set_session_draft("session_a", False)
    assert "draft" not in _read_json(root / "session_a" / "meta.json")
    assert "draft" not in _read_json(index_path)["session_a"]


# ---- AC-4：启动对账清理空草稿 ----


def test_background_sync_removes_empty_drafts_but_skips_active_and_used(sessions):
    root, index_path = sessions
    SessionStore.save_session("session_stale", [], alias="新建会话", draft=True)
    SessionStore.save_session("session_active", [], alias="新建会话", draft=True)
    SessionStore.save_session(
        "session_used", [{"role": "user", "content": "hi"}], draft=True
    )
    SessionStore.save_session("session_legacy", [], alias="旧空会话")

    SessionStore.background_sync_sessions(skip_ids={"session_active"})

    remaining = set(_read_json(index_path))
    assert "session_stale" not in remaining
    assert not (root / "session_stale").exists()
    assert "session_active" in remaining
    assert "session_used" in remaining
    assert "session_legacy" in remaining


# ---- AC-2 / AC-3：延迟构建与只构建一次 ----


def test_agent_defers_prompt_build_for_draft(sessions):
    sessions
    SessionStore.save_session("session_draft", [], draft=True)
    hooks = _Hooks()

    agent = _draft_agent(hooks)

    assert agent._prompt_pending is True
    assert agent.current_history == []
    assert "on_build_system_prompt" not in hooks.calls


def test_checker_builds_prompt_once_and_clears_draft(sessions):
    sessions
    SessionStore.save_session("session_draft", [], draft=True)
    hooks = _Hooks()
    agent = _draft_agent(hooks)

    agent.force_push("第一条消息", type="user")
    agent._checker()

    assert agent._prompt_pending is False
    assert agent.current_history[0] == {"role": "system", "content": "系统提示"}
    assert [m["role"] for m in agent.current_history].count("system") == 1
    assert SessionStore.is_session_draft("session_draft") is False

    agent.force_push("第二条消息", type="user")
    agent._checker()

    assert hooks.calls.count("on_build_system_prompt") == 1
    assert [m["role"] for m in agent.current_history].count("system") == 1


def test_empty_hook_output_still_marks_prompt_done(sessions):
    sessions
    SessionStore.save_session("session_draft", [], draft=True)
    agent = _draft_agent(_Hooks(prompt=""))

    agent.force_push("hi", type="user")
    agent._checker()

    assert agent._prompt_pending is False
    assert agent.current_history[0] == {"role": "system", "content": ""}
    assert SessionStore.is_session_draft("session_draft") is False


def test_draft_prompt_appends_project_block(sessions, monkeypatch):
    sessions
    SessionStore.save_session("session_draft", [], draft=True, project_id="proj-1")
    monkeypatch.setattr(
        project_store.ProjectStore,
        "prompt_block",
        classmethod(lambda cls, project_id: f"项目块:{project_id}"),
    )
    agent = _draft_agent()

    agent.force_push("hi", type="user")
    agent._checker()

    content = agent.current_history[0]["content"]
    assert content.startswith("系统提示")
    assert "项目块:proj-1" in content

"""会话目录、分支文件、meta 统计与索引维护（SPEC-018）。"""

from __future__ import annotations

import json

import pytest

from src.agent import session_store as store_mod
from src.agent.session_store import SessionStore


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


def test_plan_path_is_session_scoped_and_roundtrips(sessions):
    root, _ = sessions

    path = SessionStore.get_plan_path("session_a")

    assert path == str(root / "session_a" / "plan.md")
    assert SessionStore.read_session_plan("session_a") == ""
    SessionStore.save_session_plan("session_a", "第一步")
    assert SessionStore.read_session_plan("session_a") == "第一步"
    SessionStore.save_session_plan("session_a", "第二步")
    assert SessionStore.read_session_plan("session_a") == "第二步"


def test_save_main_history_and_read_back(sessions):
    root, index_path = sessions
    history = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "hi"},
    ]

    SessionStore.save_session("session_a", history, alias="甲")

    assert _read_json(root / "session_a" / "main.json") == history
    assert SessionStore.load_session_history("session_a") == history
    assert _read_json(index_path)["session_a"]["alias"] == "甲"
    assert _read_json(index_path)["session_a"]["messages_count"] == 2


def test_save_sub_branch_keeps_main_file_and_records_topology(sessions):
    root, index_path = sessions
    main_history = [{"role": "user", "content": "main"}]
    SessionStore.save_session("session_a", main_history, alias="甲")

    SessionStore.save_session(
        "session_a",
        [{"role": "user", "content": "sub"}],
        branch_id="b1",
        deliverable=["/agent_vm/a.txt"],
        action="写文件",
        consumed_tokens=5,
    )

    assert _read_json(root / "session_a" / "main.json") == main_history
    assert SessionStore.load_session_history("session_a", branch_id="b1") == [
        {"role": "user", "content": "sub"}
    ]
    meta = _read_json(root / "session_a" / "meta.json")
    assert meta["branches"]["b1"]["fork_from"] == "main"
    assert meta["branches"]["b1"]["status"] == "completed"
    assert meta["branches"]["b1"]["deliverable"] == ["/agent_vm/a.txt"]
    assert meta["branches"]["b1"]["action"] == "写文件"
    assert meta["branches"]["b1"]["consumed_tokens"] == 5
    # 子分支落盘不得覆盖主干的 index 消息数
    assert _read_json(index_path)["session_a"]["messages_count"] == len(main_history)


def test_meta_token_stats_aggregate_main_and_sub(sessions):
    sessions
    SessionStore.save_session("session_a", [], window_token=123, consumed_tokens=45)

    assert SessionStore.get_session_window_token("session_a") == 123
    assert SessionStore.get_session_consumed_tokens("session_a") == {
        "main": 45,
        "sub": 0,
        "total": 45,
    }

    SessionStore.save_session("session_a", [], branch_id="b1", consumed_tokens=7)

    assert SessionStore.get_session_consumed_tokens("session_a") == {
        "main": 45,
        "sub": 7,
        "total": 52,
    }


def test_consumed_tokens_are_preserved_when_not_explicitly_passed(sessions):
    sessions
    SessionStore.save_session("session_a", [], consumed_tokens=45)
    # 其它调用方（如 manager 的 checkpoint）不传 consumed_tokens，不能把累计值清零
    SessionStore.save_session("session_a", [], window_token=8)

    assert SessionStore.get_session_window_token("session_a") == 8
    assert SessionStore.get_session_consumed_tokens("session_a")["main"] == 45


def test_create_branch_links_parent_and_copies_history(sessions, monkeypatch):
    root, _ = sessions
    monkeypatch.setattr(
        SessionStore, "_generate_id", staticmethod(lambda: "session_new")
    )
    history = [{"role": "user", "content": "分叉点"}]

    new_id = SessionStore.create_branch(
        current_session_id="session_parent",
        current_history=history,
        branch_alias="分支",
        window_token=9,
        consumed_tokens=3,
    )

    assert new_id == "session_new"
    assert SessionStore.load_session_history(new_id) == history
    meta = _read_json(root / "session_new" / "meta.json")
    assert meta["parent_id"] == "session_parent"
    assert meta["alias"] == "分支"
    assert meta["branches"]["main"]["window_token"] == 9


def test_delete_branch_removes_file_and_meta_but_protects_main(sessions):
    root, _ = sessions
    SessionStore.save_session("session_a", [], branch_id="b1")

    assert SessionStore.delete_branch("session_a", "b1") is True

    assert not (root / "session_a" / "sub_b1.json").exists()
    assert "b1" not in _read_json(root / "session_a" / "meta.json")["branches"]
    assert SessionStore.delete_branch("session_a", "main") is False


def test_delete_session_removes_directory_and_index_entry(sessions):
    root, index_path = sessions
    SessionStore.save_session("session_a", [], alias="甲")
    SessionStore.save_session("session_b", [], alias="乙")

    SessionStore.delete_session("session_a")

    assert not (root / "session_a").exists()
    assert set(_read_json(index_path)) == {"session_b"}


def test_index_reads_only_session_prefixed_entries(sessions):
    _, index_path = sessions
    index_path.write_text(
        json.dumps({"session_a": {}, "requests": {}, "session_b": {}}),
        encoding="utf-8",
    )

    assert set(SessionStore.get_all_sessions()) == {"session_a", "session_b"}


def test_set_session_project_and_read_back(sessions):
    sessions
    SessionStore.save_session("session_a", [], alias="甲")

    SessionStore.set_session_project("session_a", "proj-1")
    assert SessionStore.get_session_project("session_a") == "proj-1"

    SessionStore.set_session_project("session_a", None)
    assert SessionStore.get_session_project("session_a") is None

    with pytest.raises(ValueError):
        SessionStore.set_session_project("not-a-session", "proj-1")


def test_set_session_paradigm_writes_meta_and_index(sessions):
    root, index_path = sessions
    SessionStore.save_session("session_a", [], alias="甲")

    SessionStore.set_session_paradigm("session_a", "developer")

    assert _read_json(root / "session_a" / "meta.json")["paradigm"] == "developer"
    assert _read_json(index_path)["session_a"]["paradigm"] == "developer"

    SessionStore.set_session_paradigm("session_a", None)

    assert "paradigm" not in _read_json(root / "session_a" / "meta.json")
    assert "paradigm" not in _read_json(index_path)["session_a"]


def test_background_sync_rebuilds_missing_index_entry(sessions):
    root, index_path = sessions
    SessionStore.save_session(
        "session_a", [{"role": "user", "content": "hi"}], alias="甲"
    )
    index_path.write_text("{}", encoding="utf-8")

    SessionStore.background_sync_sessions()

    entry = _read_json(index_path)["session_a"]
    assert entry["alias"] == "甲"
    assert entry["messages_count"] == 1

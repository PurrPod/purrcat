"""会话/聊天视图 payload 的 L0 用例（SPEC-021）。"""

from __future__ import annotations

from src.server.api import chat_views


class _Agent:
    session_id = "s1"
    consumed_tokens = 120


def test_build_token_status_uses_stored_values_for_other_session():
    """SPEC-021：非当前会话直接取落盘窗口与用量，不触发内存读取。"""
    live_calls = []

    def live_window_token():
        live_calls.append(1)
        return 999

    out = chat_views.build_token_status(
        "s2",
        _Agent(),
        max_token=1000,
        live_window_token=live_window_token,
        stored_window_token=lambda sid: 77,
        stored_consumed=lambda sid: {"main": 11, "sub": 5, "total": 16},
    )

    assert out == {
        "window_token": 77,
        "max_token": 1000,
        "consumed_main": 11,
        "consumed_sub": 5,
        "consumed_total": 16,
    }
    assert live_calls == []


def test_build_token_status_uses_live_values_for_current_session():
    """SPEC-021：当前会话取内存主用量 + 落盘子代理用量。"""
    out = chat_views.build_token_status(
        "s1",
        _Agent(),
        max_token=1000,
        live_window_token=lambda: 500,
        stored_window_token=lambda sid: 0,
        stored_consumed=lambda sid: {"main": 0, "sub": 30, "total": 30},
    )

    assert out == {
        "window_token": 500,
        "max_token": 1000,
        "consumed_main": 120,
        "consumed_sub": 30,
        "consumed_total": 150,
    }


def test_build_token_status_without_agent_or_session_defaults_to_live():
    """SPEC-021：无 Agent 且未指定会话时为全零用量 + 实时窗口。"""
    out = chat_views.build_token_status(
        "",
        None,
        max_token=1000,
        live_window_token=lambda: 42,
        stored_window_token=lambda sid: 0,
        stored_consumed=lambda sid: {"main": 0, "sub": 0, "total": 0},
    )

    assert out == {
        "window_token": 42,
        "max_token": 1000,
        "consumed_main": 0,
        "consumed_sub": 0,
        "consumed_total": 0,
    }


def test_build_session_list_normalizes_and_sorts_payload():
    """SPEC-021：会话列表字段固定，按 updated_at 倒序。"""
    sessions = {
        "a": {"alias": "A", "messages_count": 1, "updated_at": "2026-01-02"},
        "b": {},
        "c": {
            "alias": "C",
            "messages_count": 3,
            "updated_at": "2026-02-03",
            "project_id": "p1",
        },
    }

    out = chat_views.build_session_list(sessions)

    assert out == [
        {
            "id": "c",
            "alias": "C",
            "messages_count": 3,
            "updated_at": "2026-02-03",
            "project_id": "p1",
        },
        {
            "id": "a",
            "alias": "A",
            "messages_count": 1,
            "updated_at": "2026-01-02",
            "project_id": "",
        },
        {
            "id": "b",
            "alias": "b",
            "messages_count": 0,
            "updated_at": "",
            "project_id": "",
        },
    ]


def test_build_session_status_masks_non_current_session():
    """SPEC-021：非当前会话状态一律 idle，保留 compressing 标志。"""
    out = chat_views.build_session_status(
        {
            "session_id": "other",
            "state": "thinking",
            "compressing": True,
            "live_reasoning": "x",
            "live_phase": "processing",
        },
        "s1",
    )

    assert out == {
        "is_thinking": False,
        "state": "idle",
        "compressing": True,
        "live_reasoning": "",
        "phase": "idle",
    }


def test_build_session_status_current_session_phases():
    """SPEC-021：当前会话按 state 映射 is_thinking / phase，idle 清空思考内容。"""
    thinking = chat_views.build_session_status(
        {
            "session_id": "s1",
            "state": "thinking",
            "compressing": False,
            "live_reasoning": "推理中",
            "live_phase": "processing",
        },
        "s1",
    )
    assert thinking == {
        "is_thinking": True,
        "state": "thinking",
        "compressing": False,
        "live_reasoning": "推理中",
        "phase": "processing",
    }

    idle = chat_views.build_session_status(
        {"session_id": "s1", "state": "idle", "live_reasoning": "旧内容"},
        "s1",
    )
    assert idle["is_thinking"] is False
    assert idle["phase"] == "idle"
    assert idle["live_reasoning"] == ""

    aborting = chat_views.build_session_status(
        {"session_id": "s1", "state": "aborting"}, "s1"
    )
    assert aborting["phase"] == "aborting"
    assert aborting["is_thinking"] is True

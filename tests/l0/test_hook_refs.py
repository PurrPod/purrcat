"""Hook 参数里的 @ 引用解析（SPEC-004）。"""

from __future__ import annotations

import re

from src.agent import hook_handler as hook_mod
from src.agent.hook_handler import HookHandler, _expand_refs


def _handler(hooks: dict | None = None) -> HookHandler:
    return HookHandler(config_dict={"hooks": hooks or {}})


def test_expand_refs_replaces_known_alias():
    assert _expand_refs("前缀 @RULES 后缀", lambda alias: "规则") == "前缀 规则 后缀"


def test_expand_refs_keeps_alias_when_unresolved():
    assert _expand_refs("@UNKNOWN", lambda alias: None) == "@UNKNOWN"


def test_expand_refs_walks_nested_containers():
    value = {"a": ["@X", 3, {"b": "@X"}], "c": None}

    assert _expand_refs(value, lambda alias: "v", re.compile("@X")) == {
        "a": ["v", 3, {"b": "v"}],
        "c": None,
    }


def test_expand_refs_does_not_reprocess_replacement_text():
    pattern = re.compile("@[A-Z]+")

    assert (
        _expand_refs("@A @B", lambda alias: "@B" if alias == "@A" else "x", pattern)
        == "@B x"
    )


def test_user_query_expands_only_user_messages():
    handler = _handler(
        {"on_input_received": [{"injection": {"content": "收到：@USERQUERY"}}]}
    )

    results = handler.execute(
        "on_input_received",
        epoch=0,
        received_messages=[
            {"type": "user", "content": "你好"},
            {"type": "system", "content": "系统注入"},
            {"type": "user", "content": "世界"},
        ],
    )

    assert results[0]["inject_prompt"] == "收到：你好\n世界"


def test_sys_alias_uses_system_info(monkeypatch):
    handler = _handler({"on_loop_start": [{"injection": {"content": "@SYS"}}]})
    monkeypatch.setattr(handler, "_get_system_info", lambda: "SYS-INFO")

    assert handler.execute("on_loop_start", epoch=0)[0]["inject_prompt"] == "SYS-INFO"


def test_plan_alias_falls_back_without_session():
    assert (
        _handler()._ref_content("@PLAN", {"agent": None}, {}) == "暂无 BrainStorm 计划"
    )


def test_file_alias_expands_to_file_content(monkeypatch, tmp_path):
    rules = tmp_path / "RULES.md"
    rules.write_text("规则内容", encoding="utf-8")
    monkeypatch.setitem(hook_mod.PATH_ALIASES, "@RULES", str(rules))
    handler = _handler({"on_loop_start": [{"injection": {"content": "@RULES"}}]})

    assert handler.execute("on_loop_start", epoch=0)[0]["inject_prompt"] == "规则内容"


def test_missing_file_alias_keeps_reference(monkeypatch, tmp_path):
    monkeypatch.setitem(hook_mod.PATH_ALIASES, "@RULES", str(tmp_path / "missing.md"))
    handler = _handler({"on_loop_start": [{"injection": {"content": "@RULES"}}]})

    assert handler.execute("on_loop_start", epoch=0)[0]["inject_prompt"] == "@RULES"


def test_file_operation_uses_raw_path(monkeypatch, tmp_path):
    target = tmp_path / "x.md"
    target.write_text("原文", encoding="utf-8")
    monkeypatch.setitem(hook_mod.PATH_ALIASES, "@RULES", str(target))
    handler = _handler(
        {"on_loop_start": [{"file_operation": {"action": "read", "path": "@RULES"}}]}
    )

    result = handler.execute("on_loop_start", epoch=0)[0]

    assert result["success"] is True
    assert result["content"] == "原文"


def test_dynamic_content_alias_expands_without_file():
    handler = _handler({"on_loop_start": [{"injection": {"content": "@TASKSPACE"}}]})
    handler.add_alias("@TASKSPACE", content="/agent_vm/tasks")

    assert (
        handler.execute("on_loop_start", epoch=0)[0]["inject_prompt"]
        == "/agent_vm/tasks"
    )

"""Memo 段落/聚合与 BrainStorm 计划聚合的纯函数（SPEC-022 AC-3）。"""

from __future__ import annotations

import json

import pytest

from src.tool.brainstorm import _shared as brainstorm_shared
from src.tool.memo import _shared as memo_shared


def test_validate_date_format_requires_real_calendar_date():
    """SPEC-022 AC-3：日期必须是 YYYY-MM-DD 且真实存在。"""
    assert memo_shared.validate_date_format("2026-11-10")
    assert not memo_shared.validate_date_format("2026-02-30")
    assert not memo_shared.validate_date_format("2026/11/10")
    assert not memo_shared.validate_date_format("")


def test_build_memory_update_prompts_contains_both_sections():
    """SPEC-022 AC-3：MEMORY.md 提示词包含现有档案与新增内容。"""
    system, user = memo_shared.build_memory_update_prompts(
        "# 现有", ["经验 A"], ["画像 B"]
    )

    assert "overwrite_memory_md" in system
    assert "≤ 15 条" in system
    assert "【现有长期记忆档案】\n# 现有" in user
    assert "【本次新增工作经验】\n['经验 A']" in user
    assert "【本次新增用户画像】\n['画像 B']" in user


def test_build_memory_update_prompts_marks_empty_sections():
    """SPEC-022 AC-3：空档案/空输入使用括号占位，不产生空行歧义。"""
    _, user = memo_shared.build_memory_update_prompts("", [], [])

    assert "（暂无）" in user
    assert user.count("（无）") == 2


def test_extract_overwrite_content_reads_tool_arguments():
    """SPEC-022 AC-3：工具参数解析出全量 Markdown，缺键回落空串。"""
    raw = json.dumps({"new_markdown_content": "# 新记忆"}, ensure_ascii=False)

    assert memo_shared.extract_overwrite_content(raw) == "# 新记忆"
    assert memo_shared.extract_overwrite_content("{}") == ""

    with pytest.raises(json.JSONDecodeError):
        memo_shared.extract_overwrite_content("not-json")


def test_format_cached_memo_renders_yaml_or_placeholder():
    """SPEC-022 AC-3：缓存记忆以 YAML 输出，空缓存给出固定文案。"""
    assert memo_shared.format_cached_memo([]) == "当前无缓存记忆"
    assert memo_shared.format_cached_memo(None) == "当前无缓存记忆"

    dumped = memo_shared.format_cached_memo([{"role": "user", "content": "hi"}])
    assert "role: user" in dumped
    assert "content: hi" in dumped


def test_format_search_results_handles_text_dicts_and_empty():
    """SPEC-022 AC-3：检索结果兼容文本与字典列表两种返回。"""
    assert memo_shared.format_search_results("命中") == "命中"
    assert memo_shared.format_search_results("") == "未检索到相关记忆。"

    items = [{"date": "2026-11-10", "score": 0.5, "content": "内容"}]
    assert memo_shared.format_search_results(items) == (
        "[1] 2026-11-10 - 相似度: 0.5\n内容: 内容\n\n"
    )
    assert memo_shared.format_search_results([]) == "未检索到相关记忆。"


def test_render_plan_markdown_lists_main_and_branch_details():
    """SPEC-022 AC-3：总计划 Markdown 包含主干步骤与支线交付物。"""
    text = brainstorm_shared.render_plan_markdown(
        ["收集资料", "写实现"],
        [
            {
                "branch_id": "b1",
                "action": "跑测试",
                "deliverable": ["/agent_vm/test.py"],
                "depends_on": ["b0"],
            }
        ],
    )

    assert "# BrainStorm 总计划" in text
    assert "1. 收集资料" in text and "2. 写实现" in text
    assert "### b1" in text
    assert "- 任务：跑测试" in text
    assert "  - `/agent_vm/test.py`" in text
    assert "- 依赖：b0" in text


def test_render_plan_markdown_marks_empty_sections():
    """SPEC-022 AC-3：无计划/无支线时输出占位。"""
    text = brainstorm_shared.render_plan_markdown()

    assert "（无）" in text
    assert "主干步骤：0 步" in text
    assert "后台支线：0 个" in text


def test_build_create_message_keeps_order_and_plan_error():
    """SPEC-022 AC-3：创建回执的顺序与落盘失败提示逐字保持。"""
    text = brainstorm_shared.build_create_message(
        ["第一步"], [{"branch_id": "b1"}], plan_error="磁盘只读"
    )

    assert text.startswith("🚀 [系统]")
    assert "### 📌 【主干 Main 分支后续执行大纲】" in text
    assert "**Step 1**. 第一步" in text
    assert "后台支线任务 (1个)" in text
    assert "⚠️ 总计划落盘失败：磁盘只读" in text
    assert text.endswith("子任务结果出来后系统会自动通知。")


def test_find_assistant_batch_and_unanswered_calls():
    """SPEC-022 AC-3：从尾部定位 assistant 批次并筛出未应答调用。"""
    history = [
        {"role": "assistant", "tool_calls": [{"id": "a"}, {"id": "b"}]},
        {"role": "tool", "tool_call_id": "a"},
        {"role": "user", "content": "继续"},
    ]

    index = brainstorm_shared.find_assistant_tool_batch(history)
    answered, unanswered = brainstorm_shared.unanswered_tool_calls(history, index)

    assert index == 0
    assert answered == {"a"}
    assert [tc["id"] for tc in unanswered] == ["b"]

    assert brainstorm_shared.find_assistant_tool_batch([]) == -1


def test_pick_own_tool_call_prefers_id_then_function_name():
    """SPEC-022 AC-3：优先按注入的 tool_call_id 匹配，兜底按函数名。"""
    calls = [
        {"id": "x", "function": {"name": "Other"}},
        {"id": "y", "function": {"name": "BrainStorm"}},
    ]

    assert brainstorm_shared.pick_own_tool_call(calls, "x")["id"] == "x"
    assert brainstorm_shared.pick_own_tool_call(calls, None)["id"] == "y"
    assert brainstorm_shared.pick_own_tool_call(calls, "missing")["id"] == "y"
    assert brainstorm_shared.pick_own_tool_call([], None) is None


def test_build_tool_reply_is_openai_tool_message():
    """SPEC-022 AC-3：补全条目保持 role/tool_call_id/name/content 结构。"""
    reply = brainstorm_shared.build_tool_reply(
        {"id": "call_1", "function": {"name": "BrainStorm"}}, "内容"
    )

    assert reply == {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "BrainStorm",
        "content": "内容",
    }

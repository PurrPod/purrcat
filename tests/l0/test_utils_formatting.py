"""共用格式化工具与日志渲染（SPEC-015）。"""

from __future__ import annotations

import datetime

from src.utils._format import format_datetime, format_hms, human_bytes, parse_size
from src.utils.log_format import clean_log_entry, render_log_entry


def test_format_hms_handles_missing_timestamp():
    assert format_hms(0) == "??:??:??"
    expected = datetime.datetime.fromtimestamp(3600).strftime("%H:%M:%S")
    assert format_hms(3600) == expected


def test_format_datetime_default_pattern():
    ts = datetime.datetime(2026, 5, 15, 11, 32).timestamp()
    assert format_datetime(ts) == "2026-05-15 11:32:00"


def test_human_bytes_and_parse_size_round_trip_units():
    assert human_bytes(1536) == "1.5 KB"
    assert parse_size("1.5 KB") == 1500
    assert parse_size("1.5 KiB") == 1536


def test_clean_tool_call_command_is_collapsed():
    entry = {
        "card_type": "tool_call",
        "content": "🔧 助手调起工具: execute_command",
        "metadata": {"arguments": {"command": "cat > demo.py << 'PYEOF'\nprint(1)"}},
    }

    assert (
        clean_log_entry(entry) == "execute_command ➔ 写入文件: demo.py (长代码已折叠)"
    )


def test_clean_tool_call_arguments_keep_tool_name():
    entry = {
        "card_type": "tool_call",
        "content": "🔧 助手调起工具: Search(query)",
        "metadata": {"arguments": {"query": "hi"}},
    }

    assert clean_log_entry(entry) == "Search(query='hi')"


def test_clean_tool_result_reports_exit_code():
    ok = {
        "card_type": "tool",
        "content": '{"type": "text", "content": {"exit_code": 0, "output": "done"}}',
    }
    bad = {
        "card_type": "tool",
        "content": '{"type": "text", "content": {"exit_code": 2, "output": "boom"}}',
    }

    assert clean_log_entry(ok) == "✅ 执行成功 (exit_code: 0, 输出: done...)"
    assert clean_log_entry(bad) == "❌ 执行失败 (exit_code: 2, 报错: boom...)"


def test_render_log_entry_keeps_layout():
    entry = {"card_type": "thought", "content": "🔧 助手调起工具: x", "timestamp": 0}

    assert render_log_entry(entry) == (
        "[dim][??:??:??][/dim] [#88c0d0]🤖 THOUGHT  [/#88c0d0] │ x"
    )

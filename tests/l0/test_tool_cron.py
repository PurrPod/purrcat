"""Cron 纯规则：表达式校验、下次运行时间与列表格式化（SPEC-022 AC-1）。"""

from __future__ import annotations

from datetime import datetime

from src.tool.cron import cron_rules


def test_valid_trigger_time_accepts_24h_hh_mm():
    """SPEC-022 AC-1：仅 HH:MM 的 24 小时制通过。"""
    for value in ("00:00", "09:05", "23:59"):
        assert cron_rules.is_valid_trigger_time(value)

    for value in ("", "9:00", "09:0", "24:00", "09:60", "09:00:00", "ab:cd"):
        assert not cron_rules.is_valid_trigger_time(value)


def test_valid_repeat_rule_matches_schema_enum():
    """SPEC-022 AC-1：重复规则与工具 schema 的枚举一致。"""
    for rule in cron_rules.VALID_REPEAT_RULES:
        assert cron_rules.is_valid_repeat_rule(rule)

    for rule in ("", "daily", "weekly_0", "weekly_8", "WEEKLY_1"):
        assert not cron_rules.is_valid_repeat_rule(rule)


def test_next_run_time_one_shot_rolls_to_tomorrow_when_passed():
    """SPEC-022 AC-1：一次性闹钟过点后顺延到次日同一时刻。"""
    now = datetime(2026, 11, 10, 10, 0, 0)

    assert cron_rules.next_run_time("11:30", "none", now) == datetime(
        2026, 11, 10, 11, 30
    )
    assert cron_rules.next_run_time("09:00", "none", now) == datetime(
        2026, 11, 11, 9, 0
    )


def test_next_run_time_everyday_and_weekly():
    """SPEC-022 AC-1：每天与每周规则按星期几计算下一次。"""
    now = datetime(2026, 11, 10, 10, 0, 0)  # 周二

    assert cron_rules.next_run_time("09:00", "everyday", now) == datetime(
        2026, 11, 11, 9, 0
    )
    assert cron_rules.next_run_time("11:00", "weekly_3", now) == datetime(
        2026, 11, 11, 11, 0
    )
    assert cron_rules.next_run_time("09:00", "weekly_2", now) == datetime(
        2026, 11, 17, 9, 0
    )
    assert cron_rules.next_run_time("11:00", "weekly_2", now) == datetime(
        2026, 11, 10, 11, 0
    )


def test_next_run_time_returns_none_for_invalid_input():
    """SPEC-022 AC-1：非法时间或规则不产生运行时间。"""
    now = datetime(2026, 11, 10, 10, 0, 0)

    assert cron_rules.next_run_time("25:00", "none", now) is None
    assert cron_rules.next_run_time("10:00", "daily", now) is None


def test_format_cron_list_matches_tool_output():
    """SPEC-022 AC-1：列表文案与 Cron 工具逐字一致。"""
    crons = [
        {
            "id": "crn_1",
            "title": "早会",
            "trigger_time": "08:30",
            "repeat_rule": "everyday",
            "active": True,
            "description": "同步进度",
        },
        {
            "id": "crn_2",
            "title": "备份",
            "trigger_time": "23:00",
            "repeat_rule": "none",
            "active": False,
        },
    ]

    assert cron_rules.format_cron_list(crons) == (
        "- [crn_1] 早会 | 时间: 08:30 | 重复: everyday | 激活: True\n"
        "  描述: 同步进度\n"
        "- [crn_2] 备份 | 时间: 23:00 | 重复: none | 激活: False\n"
        "  描述: "
    )
    assert cron_rules.format_cron_list([]) == ""

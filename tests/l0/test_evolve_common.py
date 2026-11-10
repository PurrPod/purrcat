"""Evolve 包共用工具（JSON 解析 / 评分聚合 / 目录布局 / 报告写入，SPEC-013）。"""

from __future__ import annotations

import json

import pytest

from src.evolve.common import paths, parsing, report, scoring
from src.evolve.common.names import safe_name
from src.evolve.common.validation import validation_summary


# --------------------------------------------------------------------------- #
# JSON 解析与容错
# --------------------------------------------------------------------------- #
def test_unwrap_envelope_peels_three_layers_but_keeps_payload():
    wrapped = {"type": "port", "data": {"type": "port", "data": {"pass": True}}}
    assert parsing.unwrap_envelope(wrapped) == {"pass": True}


def test_unwrap_envelope_does_not_peel_payload_with_eval_keys():
    value = {"data": {"x": 1}, "pass": True}
    assert parsing.unwrap_envelope(value) is value


def test_try_load_dict_accepts_double_encoded_json():
    assert parsing.try_load_dict('"{\\"a\\": 1}"') == {"a": 1}


def test_try_load_dict_returns_empty_dict_for_non_dict():
    assert parsing.try_load_dict("[1, 2]") == {}
    assert parsing.try_load_dict("not json") == {}


def test_json_objects_in_skips_braces_inside_strings():
    assert list(parsing.json_objects_in('x {"a": "}"} y')) == ['{"a": "}"}']


def test_extract_eval_json_prefers_fenced_block():
    raw = '前言\n```json\n{"summary": {"passed": 1, "total": 1}}\n```\n后'
    parsed, raw_text = parsing.extract_eval_json(raw)
    assert parsed == {"summary": {"passed": 1, "total": 1}}
    assert raw_text == raw


def test_extract_eval_json_finds_last_prose_object_with_eval_keys():
    raw = '结果 {"a": 1} 与 {"pass": true, "reason": "ok"} 完'
    parsed, _ = parsing.extract_eval_json(raw)
    assert parsed == {"pass": True, "reason": "ok"}


def test_extract_eval_json_returns_none_when_unparseable():
    parsed, raw_text = parsing.extract_eval_json("完全不是 JSON")
    assert parsed is None
    assert raw_text == "完全不是 JSON"


# --------------------------------------------------------------------------- #
# 评分聚合
# --------------------------------------------------------------------------- #
def test_calculate_stats_matches_population_stddev():
    assert scoring.calculate_stats([1, 2, 3]) == {"mean": 2.0, "stddev": 0.82}
    assert scoring.calculate_stats([]) == {"mean": 0.0, "stddev": 0.0}


def test_tally_counts_pass_error_and_warning():
    cases = [
        {"pass": True, "level": "error"},
        {"pass": False, "level": "error"},
        {"pass": False, "level": "warn"},
    ]
    assert scoring.tally(cases) == {
        "total": 3,
        "passed": 1,
        "failed": 2,
        "errors": 1,
        "warnings": 1,
    }


def test_grade_eval_payload_uses_assertions_and_failed_evidence():
    passed, reason, grading = scoring.grade_eval_payload(
        {
            "eval_result": {
                "assertion_results": [
                    {"passed": True, "text": "a"},
                    {"passed": False, "text": "b", "evidence": "e"},
                ],
                "summary": {"total": 2, "passed": 2, "pass_rate": 1.0},
            }
        }
    )
    assert passed is False
    assert reason == (
        "裁判判定 1/2 条断言通过\n（通过率 100%）\n未通过的断言：\n- b：e"
    )
    assert grading["summary"]["total"] == 2


def test_grade_eval_payload_accepts_python_node_style():
    passed, reason, grading = scoring.grade_eval_payload(
        {"eval_result": {"pass": True, "reason": "ok", "grading_data": {"k": 1}}}
    )
    assert (passed, reason, grading) == (True, "ok", {"k": 1})


def test_grade_eval_payload_falls_back_to_summary():
    passed, reason, grading = scoring.grade_eval_payload(
        {"eval_result": {"summary": {"passed": 1, "total": 1}}}
    )
    assert (passed, reason, grading) == (
        True,
        "裁判判定 1/1 条断言通过",
        {"summary": {"passed": 1, "total": 1}},
    )


def test_grade_eval_payload_never_silently_fails():
    passed, reason, grading = scoring.grade_eval_payload({"eval_result": None})
    assert passed is False
    assert "裁判未产出可解析的结构化结果" in reason
    assert grading == {"raw_output": "null"}


# --------------------------------------------------------------------------- #
# 迭代目录布局
# --------------------------------------------------------------------------- #
def test_latest_iteration_idx_ignores_other_names(tmp_path):
    for name in ("iteration-1", "iteration-10", "iteration-x", "notes"):
        (tmp_path / name).mkdir()
    assert paths.latest_iteration_idx(str(tmp_path)) == 10
    assert paths.latest_iteration_idx(str(tmp_path / "missing")) == 0


def test_next_iteration_dir_allocates_after_latest(tmp_path):
    (tmp_path / "iteration-2").mkdir()
    directory, index = paths.next_iteration_dir(str(tmp_path))
    assert (directory, index) == (str(tmp_path / "iteration-3"), 3)


def test_reuse_or_next_iteration_dir_reuses_latest_without_marker(tmp_path):
    (tmp_path / "iteration-1").mkdir()
    directory, index = paths.reuse_or_next_iteration_dir(
        str(tmp_path), "eval_result.json"
    )
    assert (directory, index) == (str(tmp_path / "iteration-1"), 1)


def test_reuse_or_next_iteration_dir_opens_new_after_marker(tmp_path):
    latest = tmp_path / "iteration-1"
    latest.mkdir()
    (latest / "eval_result.json").write_text("{}", encoding="utf-8")
    directory, index = paths.reuse_or_next_iteration_dir(
        str(tmp_path), "eval_result.json"
    )
    assert (directory, index) == (str(tmp_path / "iteration-2"), 2)


# --------------------------------------------------------------------------- #
# 报告/JSON 读写
# --------------------------------------------------------------------------- #
def test_write_report_uses_fixed_filename(tmp_path):
    target = report.write_report(str(tmp_path), "<html></html>")
    assert target == str(tmp_path / "report.html")
    assert (tmp_path / "report.html").read_text(encoding="utf-8") == "<html></html>"


def test_load_json_tolerates_missing_and_broken_files(tmp_path):
    assert report.load_json(str(tmp_path / "missing.json")) is None
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert report.load_json(str(broken)) is None


def test_write_json_keeps_non_ascii_compact_contract(tmp_path):
    target = tmp_path / "x.json"
    report.write_json(str(target), {"姓名": "猫"})
    text = target.read_text(encoding="utf-8")
    assert "姓名" in text
    assert json.loads(text) == {"姓名": "猫"}


def test_now_iso_format():
    value = report.now_iso()
    assert len(value) == 19 and value[4] == "-" and value[10] == " "


# --------------------------------------------------------------------------- #
# 名称与校验结论
# --------------------------------------------------------------------------- #
def test_safe_name_messages_are_stable():
    with pytest.raises(ValueError, match="Graph 名称不能为空或非法"):
        safe_name("  ", "Graph")
    with pytest.raises(ValueError, match="AgentLoop 名称包含不支持的字符"):
        safe_name("a/b", "AgentLoop")
    assert (
        safe_name(" demo.yaml ", "AgentLoop", strip_suffixes=(".yaml", ".yml"))
        == "demo"
    )


def test_validation_summary_reports_first_five_errors():
    report_ok = {"ok": True, "errors": 0, "warnings": 2, "checks": []}
    assert validation_summary(report_ok) == (True, "校验通过（错误 0，警告 2）")

    report_bad = {
        "ok": False,
        "errors": 6,
        "warnings": 0,
        "checks": [{"title": f"t{i}", "ok": False, "level": "error"} for i in range(6)],
    }
    ok, text = validation_summary(report_bad)
    assert ok is False
    assert text == "校验未通过（6 处错误）：t0；t1；t2；t3；t4"

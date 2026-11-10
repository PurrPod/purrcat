"""Skill 评测 runner 的聚合与 Trigger 结果口径（SPEC-020）。

用替身替代真实 Task / 检索器，锁定拆分前 `skill/evaluator.py` 的
Trigger 判定文案、聚合统计、迭代目录选择与落盘字段。
"""

from __future__ import annotations

import asyncio
import json
import sys
import types

import pytest

from src.evolve.skill import runner


def _prepare_skill(tmp_path, triggers, cases):
    workplace = tmp_path / "skill_workplace" / "wid"
    skill_dir = workplace / "demo"
    (skill_dir / "evals").mkdir(parents=True)
    payload = {}
    if triggers is not None:
        payload["triggers"] = triggers
    if cases is not None:
        payload["evals"] = cases
    (skill_dir / "evals" / "evals.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: 演示\ndesc: 演示\n---\n正文\n", encoding="utf-8"
    )
    return workplace, skill_dir


def _fake_searcher_module(responses):
    class _FakeSearcher:
        def __init__(self):
            pass

        def simulate_trigger(self, query, skill):
            item = responses[query]
            if isinstance(item, Exception):
                raise item
            return item

    module = types.ModuleType("src.tool.search.skill_search")
    module.SkillSearcher = _FakeSearcher
    return module


@pytest.fixture
def fake_skill_md(monkeypatch):
    import src.utils.skill_helper as skill_helper

    monkeypatch.setattr(
        skill_helper,
        "_parse_skill_md",
        lambda path: {
            "metadata": {"name": "demo", "description": "演示"},
            "content": "正文",
        },
    )


def test_aggregate_results_keeps_order_and_stats():
    """SPEC-020 AC-3：用例顺序与 with_skill 统计口径不变。"""
    cases, summary = runner._aggregate_results(
        [
            (
                {"case_id": "a", "pass": True, "time_seconds": 1.5, "tokens": 10},
                1.5,
                10,
            ),
            (
                {"case_id": "b", "pass": False, "time_seconds": 2.5, "tokens": 20},
                2.5,
                20,
            ),
        ]
    )

    assert [case["case_id"] for case in cases] == ["a", "b"]
    assert summary == {
        "with_skill": {
            "pass_rate": {"mean": 0.5, "stddev": 0.5},
            "time_seconds": {"mean": 2.0, "stddev": 0.5},
            "tokens": {"mean": 15.0, "stddev": 5.0},
        }
    }


def test_aggregate_results_empty_input_uses_zero_stats():
    """SPEC-020 AC-3：无用例时统计归零，不抛异常。"""
    cases, summary = runner._aggregate_results([])
    assert cases == []
    assert summary["with_skill"]["pass_rate"] == {"mean": 0.0, "stddev": 0.0}


def test_trigger_eval_status_and_details(tmp_path, monkeypatch, fake_skill_md):
    """SPEC-020 AC-3：应触发/激发失败/反例拦截/反例误触/框架崩溃文案不变。"""
    workplace, _ = _prepare_skill(
        tmp_path,
        [
            {"query": "q-hit", "should_trigger": True},
            {"query": "q-miss", "should_trigger": True},
            {"query": "q-negative", "should_trigger": False},
            {"query": "q-leak", "should_trigger": False},
            {"query": "q-boom", "should_trigger": True},
        ],
        None,
    )
    responses = {
        "q-hit": {"is_triggered": True, "rank": 1, "score": 0.9, "competitors": []},
        "q-miss": {
            "is_triggered": False,
            "rank": None,
            "score": 0.2,
            "competitors": [],
        },
        "q-negative": {
            "is_triggered": False,
            "rank": None,
            "score": 0.1,
            "competitors": [],
        },
        "q-leak": {
            "is_triggered": True,
            "rank": 2,
            "score": 0.8,
            "competitors": ["other"],
        },
        "q-boom": RuntimeError("boom"),
    }
    monkeypatch.setitem(
        sys.modules, "src.tool.search.skill_search", _fake_searcher_module(responses)
    )
    monkeypatch.setattr(runner, "AGENT_VM_DIR", str(tmp_path))
    monkeypatch.setattr(runner, "render_skill_report", lambda *args: "")

    message = runner._run_trigger_evals("wid", "demo")

    assert (
        message
        == "🎯 Trigger 激发路由唤醒率 2/5，报告已生成（iteration-1/report.html）。"
    )
    result = json.loads(
        (workplace / "iteration-1" / "trigger_result.json").read_text(encoding="utf-8")
    )
    assert result["total"] == 5
    assert result["passed"] == 2
    assert result["skill_name"] == "demo"
    assert result["iteration"] == 1
    assert len(result["generated_at"]) == 19
    by_query = {case["query"]: case for case in result["cases"]}
    assert (by_query["q-hit"]["status"], by_query["q-hit"]["detail"]) == (
        "pass",
        "唤醒成功（排名第 1，得分 0.9）",
    )
    assert (by_query["q-miss"]["status"], by_query["q-miss"]["detail"]) == (
        "fail",
        "激发失败（得分 0.2，未进 Top 3 或低于唤醒阈值）",
    )
    assert (by_query["q-negative"]["status"], by_query["q-negative"]["detail"]) == (
        "pass",
        "反例拦截成功（技能保持静默）",
    )
    assert (by_query["q-leak"]["status"], by_query["q-leak"]["detail"]) == (
        "fail",
        "反例拦截失败（不该触发却排名第 2）",
    )
    assert (by_query["q-boom"]["status"], by_query["q-boom"]["detail"]) == (
        "fail",
        "框架崩溃: boom",
    )
    assert [case["index"] for case in result["cases"]] == [1, 2, 3, 4, 5]


def test_trigger_eval_reuses_target_iteration_dir(tmp_path, monkeypatch, fake_skill_md):
    """SPEC-020 AC-3：传入 target_dir 时结果写入该代并解析其编号。"""
    workplace, _ = _prepare_skill(
        tmp_path, [{"query": "q", "should_trigger": True}], None
    )
    responses = {
        "q": {"is_triggered": True, "rank": 1, "score": 0.5, "competitors": []}
    }
    monkeypatch.setitem(
        sys.modules, "src.tool.search.skill_search", _fake_searcher_module(responses)
    )
    monkeypatch.setattr(runner, "AGENT_VM_DIR", str(tmp_path))
    target = workplace / "iteration-7"
    target.mkdir()

    runner._run_trigger_evals("wid", "demo", str(target))

    result = json.loads((target / "trigger_result.json").read_text(encoding="utf-8"))
    assert result["iteration"] == 7


def test_trigger_eval_reports_missing_inputs(tmp_path, monkeypatch):
    """SPEC-020 AC-3：缺少 evals.json / triggers / SKILL.md 的提示逐字不变。"""
    monkeypatch.setattr(runner, "AGENT_VM_DIR", str(tmp_path))
    workplace = tmp_path / "skill_workplace" / "wid"
    skill_dir = workplace / "demo"
    skill_dir.mkdir(parents=True)

    assert runner._run_trigger_evals("wid", "demo") == (
        f"测试失败：未找到 {skill_dir / 'evals' / 'evals.json'}"
    )

    (skill_dir / "evals").mkdir()
    (skill_dir / "evals" / "evals.json").write_text("{}", encoding="utf-8")
    assert runner._run_trigger_evals("wid", "demo") == (
        "Trigger 报告：evals.json 中没有任何 trigger 测试用例。"
    )

    (skill_dir / "evals" / "evals.json").write_text(
        '{"triggers": [{"query": "q"}]}', encoding="utf-8"
    )
    assert (
        runner._run_trigger_evals("wid", "demo") == "测试失败：沙盒内未找到 SKILL.md。"
    )


def test_async_run_evals_aggregates_and_persists(tmp_path, monkeypatch):
    """SPEC-020 AC-4：盲测编排复用 Iteration、聚合落盘与返回文案不变。"""
    workplace, _ = _prepare_skill(tmp_path, None, [{"id": "a"}, {"id": "b"}])
    monkeypatch.setattr(runner, "AGENT_VM_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr(runner, "render_skill_report", lambda *args: calls.append(args))

    async def fake_case(case, *args):
        if case["id"] == "a":
            return (
                {"case_id": "a", "pass": True, "time_seconds": 1.0, "tokens": 10},
                1.0,
                10,
            )
        return (
            {"case_id": "b", "pass": False, "time_seconds": 3.0, "tokens": 20},
            3.0,
            20,
        )

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(runner, "_run_single_eval_case", fake_case)
    monkeypatch.setattr(runner.asyncio, "sleep", no_sleep)

    message = asyncio.run(runner._async_run_evals("wid", "demo"))

    assert message == (
        "📊 盲测通过 1/2，平均 2.0s / 15.0 tokens，"
        "报告已生成（iteration-1/report.html）。"
    )
    iteration_dir = workplace / "iteration-1"
    assert json.loads(
        (iteration_dir / "benchmark.json").read_text(encoding="utf-8")
    ) == {
        "run_summary": {
            "with_skill": {
                "pass_rate": {"mean": 0.5, "stddev": 0.5},
                "time_seconds": {"mean": 2.0, "stddev": 1.0},
                "tokens": {"mean": 15.0, "stddev": 5.0},
            }
        },
        "cases": [
            {"case_id": "a", "pass": True, "time_seconds": 1.0, "tokens": 10},
            {"case_id": "b", "pass": False, "time_seconds": 3.0, "tokens": 20},
        ],
    }
    result = json.loads(
        (iteration_dir / "eval_result.json").read_text(encoding="utf-8")
    )
    assert result["total"] == 2
    assert result["passed"] == 1
    assert result["summary"]["tokens"]["mean"] == 15.0
    assert calls == [(str(workplace), str(iteration_dir), 1, "demo")]


def test_async_run_evals_new_iteration_runs_triggers_first(tmp_path, monkeypatch):
    """SPEC-020 AC-4：new_iteration=True 先新开一代并跑 Trigger，再跑盲测。"""
    workplace, _ = _prepare_skill(tmp_path, None, [{"id": "a"}])
    (workplace / "iteration-1").mkdir()
    monkeypatch.setattr(runner, "AGENT_VM_DIR", str(tmp_path))
    monkeypatch.setattr(runner, "render_skill_report", lambda *args: "")
    order = []
    monkeypatch.setattr(
        runner, "_run_trigger_evals", lambda *args: order.append(("trigger", args))
    )

    async def fake_case(case, *args):
        order.append(("case", args))
        return (
            {"case_id": "a", "pass": True, "time_seconds": 1.0, "tokens": 1},
            1.0,
            1,
        )

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(runner, "_run_single_eval_case", fake_case)
    monkeypatch.setattr(runner.asyncio, "sleep", no_sleep)

    asyncio.run(runner._async_run_evals("wid", "demo", new_iteration=True))

    assert order[0] == ("trigger", ("wid", "demo", str(workplace / "iteration-2")))
    assert order[1][0] == "case"
    assert (workplace / "iteration-2" / "eval_result.json").is_file()

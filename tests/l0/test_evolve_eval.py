"""Evolve 评估流水线的纯逻辑阶段（SPEC-013）。"""

from __future__ import annotations

from src.evolve.mcp.evaluator import _execution_passed
from src.evolve.sensor.evaluator import _static_checks, _summarize_cases
from src.evolve.skill.evaluator import _aggregate_results


def _sensor_script(with_issues: bool = False) -> str:
    if with_issues:
        return (
            "import os\n"
            "import sys\n"
            "TOKEN = os.environ.get('MY_TOKEN')\n"
            "API_KEY = '0123456789abcdef0123'\n"
            "sys.exit(1)\n"
        )
    return (
        "# /// script\n"
        "# ///\n"
        "import os\n"
        "import sys\n"
        "sys.stdout = sys.stderr\n"
        "TOKEN = os.environ.get('MY_TOKEN')\n"
    )


def test_sensor_static_checks_all_green():
    cases = _static_checks(
        _sensor_script(), {"name": "demo", "env": {"MY_TOKEN": ""}}, "", "demo"
    )
    by_id = {case["id"]: case for case in cases}
    assert by_id["pep723"]["pass"] is True
    assert by_id["stdout_redirect"]["pass"] is True
    assert by_id["no_force_exit"]["pass"] is True
    assert by_id["no_hardcoded_secret"]["pass"] is True
    assert by_id["config_valid"]["pass"] is True
    assert by_id["env_declared"]["pass"] is True
    assert "env_unused" not in by_id
    assert all(case["layer"] == "L0" for case in cases)


def test_sensor_static_checks_surface_every_violation():
    config = {"name": "other", "env": {"MY_TOKEN": "", "UNUSED": ""}}
    cases = _static_checks(_sensor_script(True), config, "", "demo")
    by_id = {case["id"]: case for case in cases}
    assert by_id["pep723"]["pass"] is False
    assert by_id["stdout_redirect"]["pass"] is False
    assert by_id["no_force_exit"]["pass"] is False
    assert by_id["no_hardcoded_secret"]["pass"] is False
    assert by_id["config_valid"]["pass"] is False
    # MY_TOKEN 在代码里读取但配置的 name 不符，声明集合仍来自 env 键。
    assert by_id["env_unused"]["pass"] is False
    assert by_id["env_unused"]["level"] == "warn"


def test_sensor_static_checks_report_config_parse_error():
    cases = _static_checks(_sensor_script(), {}, "JSON 解析失败", "demo")
    by_id = {case["id"]: case for case in cases}
    assert by_id["config_valid"]["pass"] is False
    assert by_id["config_valid"]["detail"] == "JSON 解析失败"
    # 配置读不出来时 declared 为空，代码读取的 env 键必然被判为未声明。
    assert by_id["env_declared"]["pass"] is False


def test_sensor_summary_counts_errors_and_warnings():
    cases = [
        {"pass": True, "level": "error"},
        {"pass": False, "level": "error"},
        {"pass": False, "level": "warn"},
    ]
    assert _summarize_cases(cases) == {
        "passed": 1,
        "total": 3,
        "errors": 1,
        "warnings": 1,
    }


def test_mcp_execution_verdict_prefers_explicit_verdict():
    assert _execution_passed({"verdict": "pass", "status": "exception"}) is True
    assert _execution_passed({"verdict": "fail", "status": "success"}) is False
    # 旧产物没有 verdict 时回退到 status。
    assert _execution_passed({"status": "success"}) is True
    assert _execution_passed({"status": "exception"}) is False
    # verdict 显式为 null 也按旧产物处理。
    assert _execution_passed({"verdict": None, "status": "success"}) is True


def test_skill_aggregate_results_builds_run_summary():
    cases, summary = _aggregate_results(
        [
            (
                {
                    "case_id": "a",
                    "pass": True,
                    "time_seconds": 1.5,
                    "tokens": 10,
                    "reason": "",
                },
                1.5,
                10,
            ),
            (
                {
                    "case_id": "b",
                    "pass": False,
                    "time_seconds": 2.5,
                    "tokens": 20,
                    "reason": "bad",
                },
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

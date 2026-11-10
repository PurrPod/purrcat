"""Evolve 共用评分聚合与裁判结果归一化。"""

import math

from .parsing import extract_eval_json


def calculate_stats(values: list[float]) -> dict:
    if not values:
        return {"mean": 0.0, "stddev": 0.0}
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    stddev = math.sqrt(variance)
    return {"mean": round(mean, 2), "stddev": round(stddev, 2)}


def tally(cases: list[dict]) -> dict:
    """按 pass/level 统计用例总数、通过、失败、硬伤与告警。"""
    passed = sum(1 for case in cases if case.get("pass"))
    errors = sum(
        1 for case in cases if not case.get("pass") and case.get("level") == "error"
    )
    warnings = sum(
        1 for case in cases if not case.get("pass") and case.get("level") == "warn"
    )
    return {
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "errors": errors,
        "warnings": warnings,
    }


def grade_eval_payload(outputs: dict) -> tuple:
    """把裁判产出的 eval_result 解析成 (is_pass, reason, grading_data)。

    解析不出来时必须给出带原文片段的理由，禁止静默判负。
    """
    eval_res, raw_output = extract_eval_json(outputs.get("eval_result"))

    if eval_res is None:
        return (
            False,
            "裁判未产出可解析的结构化结果（输出既不是 JSON，"
            f"也抠不出断言数组）：{raw_output[:300]}",
            {"raw_output": raw_output[:4000]},
        )

    gd = eval_res.get("grading_data")
    gd = gd if isinstance(gd, dict) else {}

    assertion_results = eval_res.get("assertion_results")
    if not (isinstance(assertion_results, list) and assertion_results):
        assertion_results = gd.get("assertion_results")
    assertion_results = assertion_results if isinstance(assertion_results, list) else []

    stats = eval_res.get("summary")
    if not isinstance(stats, dict) or not stats:
        stats = gd.get("summary")
    stats = stats if isinstance(stats, dict) else {}

    if assertion_results:
        # 断言级结果最可信：通过数直接按 passed 字段现算，不采信自报统计
        passed = sum(
            1
            for r in assertion_results
            if isinstance(r, dict) and r.get("passed") is True
        )
        total = len(assertion_results)
        if not stats.get("total"):
            stats = {
                "passed": passed,
                "failed": total - passed,
                "total": total,
                "pass_rate": round(passed / total, 2),
            }
        reason_lines = [f"裁判判定 {passed}/{total} 条断言通过"]
        if isinstance(stats.get("pass_rate"), (int, float)):
            reason_lines.append(f"（通过率 {stats['pass_rate'] * 100:.0f}%）")
        failed_items = [
            r for r in assertion_results if isinstance(r, dict) and not r.get("passed")
        ]
        if failed_items:
            reason_lines.append("未通过的断言：")
            reason_lines.extend(
                f"- {r.get('text', '')}：{r.get('evidence', '无证据')}"
                for r in failed_items
            )
        return (
            passed == total,
            "\n".join(reason_lines),
            {"assertion_results": assertion_results, "summary": stats},
        )

    if eval_res.get("reason"):
        # Python 计算节点风格：{pass, reason, grading_data}
        return bool(eval_res.get("pass")), eval_res.get("reason"), gd

    if stats.get("total"):
        passed = int(stats.get("passed") or 0)
        total = int(stats["total"])
        return (
            passed == total,
            f"裁判判定 {passed}/{total} 条断言通过",
            {"summary": stats},
        )

    return (
        False,
        f"裁判返回的 JSON 缺少断言数组与统计字段：{raw_output[:300]}",
        {"raw_output": raw_output[:4000]},
    )

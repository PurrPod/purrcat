"""Skill 评测报告组装（SPEC-020）。

把 trigger_result / eval_result / trace_meta 渲染为单一 report.html（瑞士风）。
报告即输出物：不列文件清单、不贴路径，只呈现结论与证据。
"""

import os

from src.evolve.common.report import (
    load_json as _load_json,
    now_iso as _now_iso,
    write_report as _write_report,
)


def _build_token_savings_blocks(trace_meta, evals, H) -> list:
    """trace2skill 专属：图标化展示技能为后台盲测省下的 token。"""
    blocks = []
    if not (trace_meta and evals and evals.get("cases")):
        return blocks
    baseline = int(trace_meta.get("consumed_total") or 0)
    token_vals = [int(c.get("tokens") or 0) for c in evals["cases"]]
    if baseline > 0 and token_vals:
        mean_tokens = int(round(sum(token_vals) / len(token_vals)))
        # 用例全部崩溃时 tokens 全为 0，此时对比会把整个会话累计量当成“节省量”，故不渲染
        if mean_tokens > 0:
            blocks.append(
                H.token_savings(baseline - mean_tokens, baseline, mean_tokens)
            )
        else:
            blocks.append(
                H.note("盲测未产出有效 token 数据，本轮不做 token 节省对比。")
            )
    return blocks


def _build_overview(evals, trigger) -> list:
    overview = []
    if evals:
        total, passed = evals.get("total", 0), evals.get("passed", 0)
        rsum = evals.get("summary", {}) or {}
        overview.append(
            {
                "label": "盲测通过",
                "value": f"{passed}/{total}",
                "icon_name": "target",
                "tone": "ok" if total and passed == total else "",
            }
        )
        token_mean = (rsum.get("tokens") or {}).get("mean")
        if token_mean is not None:
            overview.append(
                {
                    "label": "平均 Tokens",
                    "value": f"{token_mean:g}",
                    "icon_name": "coin",
                }
            )
        time_mean = (rsum.get("time_seconds") or {}).get("mean")
        if time_mean is not None:
            overview.append(
                {
                    "label": "平均耗时",
                    "value": f"{time_mean:g}",
                    "unit": "s",
                    "icon_name": "clock",
                }
            )
    if trigger:
        overview.append(
            {
                "label": "Trigger 唤醒率",
                "value": f"{trigger.get('passed', 0)}/{trigger.get('total', 0)}",
                "icon_name": "zap",
                "tone": "accent"
                if trigger.get("passed") == trigger.get("total")
                else "",
            }
        )
    return overview


def _build_trigger_block(trigger, section_no: int, H):
    items = []
    for c in trigger.get("cases", []):
        expect = "应触发" if c.get("should_trigger") else "静默阻断（反例）"
        competitors = "、".join(c.get("competitors") or []) or "无"
        items.append(
            {
                "title": f"案例 {c.get('index')}：{c.get('query', '')}",
                "status": c.get("status", ""),
                "meta": [("期望", expect), ("结果", c.get("detail", ""))],
                "notes": [f"语义竞争者（Top 3）：{competitors}"],
            }
        )
    return H.section(f"{section_no:02d}", "Trigger 激发测试", H.cases(items))


def _build_evals_block(evals, section_no: int, H):
    items = []
    for c in evals.get("cases", []):
        notes = [c.get("reason", "")] if c.get("reason") else []
        items.append(
            {
                "title": f"用例 {c.get('case_id', '')}",
                "status": "pass" if c.get("pass") else "fail",
                "meta": [
                    ("耗时", f"{c.get('time_seconds')}s"),
                    ("Tokens", str(c.get("tokens"))),
                ],
                "notes": notes,
            }
        )
    return H.section(f"{section_no:02d}", "自动化盲测（with_skill）", H.cases(items))


def render_skill_report(
    workplace_root: str, iteration_dir: str, iteration_idx: int, skill_name: str
) -> str:
    """将 trigger_result / eval_result / trace_meta 渲染为单一 report.html（瑞士风）。"""
    from src.evolve import report_html as H

    trigger = _load_json(os.path.join(iteration_dir, "trigger_result.json"))
    evals = _load_json(os.path.join(iteration_dir, "eval_result.json"))
    trace_meta = _load_json(os.path.join(workplace_root, "trace_meta.json"))

    blocks = _build_token_savings_blocks(trace_meta, evals, H)

    overview = _build_overview(evals, trigger)
    if overview:
        blocks.append(H.stats(overview, cols=min(len(overview), 4)))

    section_no = 1
    if trigger:
        blocks.append(_build_trigger_block(trigger, section_no, H))
        section_no += 1

    if evals:
        blocks.append(_build_evals_block(evals, section_no, H))
        section_no += 1

    if not trigger and not evals:
        blocks.append(H.note("本轮迭代尚无可用结果。"))

    meta = [
        ("技能", skill_name),
        ("迭代", f"Iteration {iteration_idx}"),
        ("工作区", os.path.basename(os.path.dirname(iteration_dir))),
        ("生成时间", _now_iso()),
    ]
    html = H.page(
        title=f"{skill_name} · 技能评测报告",
        subtitle="Trigger 激发路由与隔离沙盒盲测结果。数据来自影子检索与双 Agent 裁判实跑，非 Agent 自报。",
        meta=meta,
        blocks=blocks,
        kicker="PURRCAT · SKILL FACTORY",
        footer_left="Skill Evolution Report",
        footer_right=f"Iteration {iteration_idx:02d}",
    )
    _write_report(iteration_dir, html)
    return html

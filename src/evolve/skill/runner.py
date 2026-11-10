"""Skill 评测执行编排（SPEC-020）。

Trigger 激发路由、单用例隔离协程、并发聚合与盲测落盘；报告渲染委托 report.py。
并发错位间隔、迭代目录复用规则与结果字段是评测契约的一部分。
"""

import asyncio
import json
import os
import re
import shutil

from src.harness.process import Task
from src.utils.config import AGENT_VM_DIR

from src.evolve.common.paths import (
    latest_iteration_idx as _get_latest_iteration_idx,
    next_iteration_dir as _get_next_iteration_dir,
    reuse_or_next_iteration_dir,
)
from src.evolve.common.report import (
    now_iso as _now_iso,
    write_json as _write_json,
)
from src.evolve.common.scoring import (
    calculate_stats as _calculate_stats,
    grade_eval_payload as _grade_eval_payload,
)
from src.evolve.skill.prompts import build_expected_output_prompt
from src.evolve.skill.report import render_skill_report


def _get_eval_iteration_dir(workplace_root: str) -> tuple[str, int]:
    """盲测归入最近一轮 Trigger 测试的迭代目录（同目录含 trigger + 盲测结果）。"""
    return reuse_or_next_iteration_dir(workplace_root, "eval_result.json")


def _run_trigger_evals(workplace_id: str, skill_name: str, target_dir: str = "") -> str:
    """以影子节点方式将沙盒技能注入检索快照，跑 triggers 激发测试

    target_dir 为空时新开一代；传入目录时把结果写进该代（手动「运行评测」会新开一代后复用它）。
    """
    workplace_root = os.path.join(AGENT_VM_DIR, "skill_workplace", workplace_id)
    dev_skill_dir = os.path.join(workplace_root, skill_name)
    evals_file = os.path.join(dev_skill_dir, "evals", "evals.json")

    if not os.path.exists(evals_file):
        return f"测试失败：未找到 {evals_file}"

    try:
        with open(evals_file, "r", encoding="utf-8") as f:
            evals_data = json.load(f)
    except json.JSONDecodeError:
        return "测试失败：evals.json 格式错误，无法解析为有效的 JSON。"

    triggers = evals_data.get("triggers", [])
    if not triggers:
        return "Trigger 报告：evals.json 中没有任何 trigger 测试用例。"

    # 解析沙盒 SKILL.md，组装影子技能节点
    skill_md_path = os.path.join(dev_skill_dir, "SKILL.md")
    if not os.path.exists(skill_md_path):
        return "测试失败：沙盒内未找到 SKILL.md。"

    from pathlib import Path
    from src.utils.skill_helper import _parse_skill_md
    from src.tool.search.skill_search import SkillSearcher

    parsed = _parse_skill_md(Path(skill_md_path))
    metadata = parsed.get("metadata", {})
    sandbox_skill = {
        "name": metadata.get("name", skill_name),
        "description": metadata.get("description", metadata.get("desc", "")),
        "content": parsed.get("content", ""),
        "dir_name": skill_name,
    }
    if not sandbox_skill["description"]:
        return "测试失败：SKILL.md 的 frontmatter 缺少 description，无法参与激发检索。"

    searcher = SkillSearcher()

    if target_dir:
        iteration_dir = target_dir
        match = re.match(r"iteration-(\d+)$", os.path.basename(target_dir))
        iteration_idx = (
            int(match.group(1)) if match else _get_latest_iteration_idx(workplace_root)
        )
    else:
        iteration_dir, iteration_idx = _get_next_iteration_dir(workplace_root)
    os.makedirs(iteration_dir, exist_ok=True)

    trigger_cases = []
    success = 0

    for idx, t_case in enumerate(triggers):
        query = t_case.get("query", "")
        should_trigger = t_case.get("should_trigger", True)
        item = {
            "index": idx + 1,
            "query": query,
            "should_trigger": bool(should_trigger),
        }

        try:
            res = searcher.simulate_trigger(query, sandbox_skill)
        except Exception as e:
            item.update(
                {
                    "hit": False,
                    "status": "fail",
                    "detail": f"框架崩溃: {e}",
                    "rank": None,
                    "score": None,
                    "competitors": [],
                }
            )
            trigger_cases.append(item)
            continue

        hit = res["is_triggered"]
        item.update(
            {
                "hit": bool(hit),
                "rank": res.get("rank"),
                "score": res.get("score"),
                "competitors": res.get("competitors", []),
            }
        )
        if should_trigger and hit:
            item["status"] = "pass"
            item["detail"] = f"唤醒成功（排名第 {res['rank']}，得分 {res['score']}）"
            success += 1
        elif should_trigger and not hit:
            item["status"] = "fail"
            item["detail"] = (
                f"激发失败（得分 {res['score']}，未进 Top 3 或低于唤醒阈值）"
            )
        elif not should_trigger and not hit:
            item["status"] = "pass"
            item["detail"] = "反例拦截成功（技能保持静默）"
            success += 1
        else:
            item["status"] = "fail"
            item["detail"] = f"反例拦截失败（不该触发却排名第 {res['rank']}）"
        trigger_cases.append(item)

    _write_json(
        os.path.join(iteration_dir, "trigger_result.json"),
        {
            "skill_name": skill_name,
            "iteration": iteration_idx,
            "generated_at": _now_iso(),
            "total": len(triggers),
            "passed": success,
            "cases": trigger_cases,
        },
    )
    render_skill_report(workplace_root, iteration_dir, iteration_idx, skill_name)

    return (
        f"🎯 Trigger 激发路由唤醒率 {success}/{len(triggers)}，"
        f"报告已生成（iteration-{iteration_idx}/report.html）。"
    )


def _format_and_save_trace(memory_path: str, output_trace_path: str):
    trace_lines = ["# Trace(U:user;A:assistant;C:calltool;R:result's snip)"]
    if os.path.exists(memory_path):
        try:
            with open(memory_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    msg = json.loads(line)
                    role = msg.get("role")
                    if role == "user":
                        content = msg.get("content", "")
                        trace_lines.append(f'\n[U]"{content}"')
                    elif role == "assistant":
                        content = msg.get("content", "")
                        reasoning = msg.get("reasoning_content", "")
                        a_text = ""
                        if reasoning:
                            a_text += f"{reasoning}\n"
                        if content:
                            a_text += f"{content}"
                        if a_text.strip():
                            trace_lines.append(f"\n[A]{a_text.strip()}")
                        tool_calls = msg.get("tool_calls", [])
                        for tc in tool_calls:
                            func_name = tc.get("function", {}).get(
                                "name", "unknown_tool"
                            )
                            trace_lines.append(f"\n[C]{func_name}")
                    elif role == "tool":
                        raw_content = msg.get("content", "")
                        snip = ""
                        try:
                            parsed = json.loads(raw_content)
                            if isinstance(parsed, dict):
                                if (
                                    "metadata" in parsed
                                    and "snip" in parsed["metadata"]
                                ):
                                    snip = parsed["metadata"]["snip"]
                                elif "summary" in parsed:
                                    snip = str(parsed["summary"])
                                else:
                                    snip = raw_content[:100] + "..."
                            else:
                                snip = raw_content[:100] + "..."
                        except json.JSONDecodeError:
                            snip = raw_content[:100] + "..."
                        snip = snip if snip else "执行成功 (无简述)"
                        trace_lines.append(f"\n[R]{snip}")
        except Exception as e:
            trace_lines.append(f"\n[Error] 解析轨迹失败: {str(e)}")
    else:
        trace_lines.append("\n[Error] 未找到测试工人的记忆文件")

    with open(output_trace_path, "w", encoding="utf-8") as out_f:
        out_f.write("\n".join(trace_lines))


async def _run_single_eval_case(
    case, dev_skill_dir, iteration_dir, workplace_id, skill_name, iteration_idx
):
    try:
        case_id = case.get("id", "unknown")
        eval_run_dir = os.path.join(iteration_dir, f"eval-{case_id}", "with_skill")
        sandbox_eval_dir = f"/agent_vm/skill_workplace/{workplace_id}/iteration-{iteration_idx}/eval-{case_id}/with_skill"

        def ignore_eval_files(dir_path, contents):
            return ["evals", "README.md", ".git", ".gitignore", "__pycache__"]

        # 同一代重跑评测时先清掉上一轮残留目录，否则 copytree 会撞上已存在目录（WinError 183）
        shutil.rmtree(eval_run_dir, ignore_errors=True)
        shutil.copytree(dev_skill_dir, eval_run_dir, ignore=ignore_eval_files)
        outputs_dir = os.path.join(eval_run_dir, "outputs")
        os.makedirs(outputs_dir, exist_ok=True)

        assets_list = case.get("files", case.get("assets", []))
        for asset_path in assets_list:
            src_asset = os.path.join(dev_skill_dir, asset_path)
            if os.path.exists(src_asset):
                dst_asset = os.path.join(eval_run_dir, os.path.basename(asset_path))
                if os.path.isdir(src_asset):
                    shutil.copytree(src_asset, dst_asset, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_asset, dst_asset)

        prompt = case.get("prompt", "")
        expected = case.get("expected_output", "")
        assertions = case.get("assertions", [])
        qa_expected = build_expected_output_prompt(expected, assertions)

        host_skill_md_path = os.path.abspath(os.path.join(eval_run_dir, "SKILL.md"))

        task = Task(
            task_name=f"Eval_{skill_name}_{case_id}",
            inputs={
                "host_skill_md_path": host_skill_md_path,
                "workplace_dir": sandbox_eval_dir,
                "prompt": prompt,
                "expected_output": qa_expected,
            },
            graph_name="skill_eval",
            # 💡 核心修复：注入 iteration_idx 确保每次迭代生成独立的 Task 存档
            task_id=f"eval_{workplace_id}_iter{iteration_idx}_{case_id}",
        )

        res = await task.run()

        elapsed = task.execution_time
        tokens = task.total_tokens

        # 清洗并存储隔离区内独立的 trace.md
        agent_memory_path = os.path.join(
            task.checkpoint_dir, "nodes", "nd_agent_exec", "memory.jsonl"
        )
        trace_filepath = os.path.join(eval_run_dir, "trace.md")
        _format_and_save_trace(agent_memory_path, trace_filepath)

        timing_data = {"total_tokens": tokens, "duration_ms": int(elapsed * 1000)}
        with open(os.path.join(eval_run_dir, "timing.json"), "w") as f:
            json.dump(timing_data, f, indent=2)

        is_pass = False
        reason = "未知错误"
        grading_data = {}

        if res.get("status") == "success":
            is_pass, reason, grading_data = _grade_eval_payload(res.get("outputs", {}))

            with open(
                os.path.join(eval_run_dir, "grading.json"), "w", encoding="utf-8"
            ) as f:
                json.dump(grading_data, f, ensure_ascii=False, indent=2)
        else:
            reason = res.get("message", "执行异常中断")
            grading_data = {"summary": {"passed": False, "reason": reason}}
            with open(
                os.path.join(eval_run_dir, "grading.json"), "w", encoding="utf-8"
            ) as f:
                json.dump(grading_data, f, ensure_ascii=False, indent=2)

        try:
            from src.tool.bash import close_session

            await asyncio.to_thread(close_session, task.task_id)
        except Exception:
            pass

        benchmark_item = {
            "case_id": case_id,
            "pass": is_pass,
            "time_seconds": round(elapsed, 2),
            "tokens": tokens,
            "reason": reason,
        }

        return benchmark_item, elapsed, tokens

    except Exception as e:
        return (
            {
                "case_id": case.get("id", "unknown"),
                "pass": False,
                "time_seconds": 0,
                "tokens": 0,
                "reason": f"框架崩溃: {str(e)}",
            },
            0.0,
            0,
        )


def _aggregate_results(results: list) -> tuple:
    """把并发的单用例结果聚合为报告用例与 with_skill 统计摘要。"""
    benchmark_cases = [benchmark_item for benchmark_item, _, _ in results]

    pass_values = [1.0 if c["pass"] else 0.0 for c in benchmark_cases]
    time_values = [c["time_seconds"] for c in benchmark_cases]
    token_values = [c["tokens"] for c in benchmark_cases]

    run_summary = {
        "with_skill": {
            "pass_rate": _calculate_stats(pass_values),
            "time_seconds": _calculate_stats(time_values),
            "tokens": _calculate_stats(token_values),
        }
    }
    return benchmark_cases, run_summary


async def _async_run_evals(
    workplace_id: str, skill_name: str, new_iteration: bool = False
) -> str:
    workplace_root = os.path.join(AGENT_VM_DIR, "skill_workplace", workplace_id)
    dev_skill_dir = os.path.join(workplace_root, skill_name)
    evals_file = os.path.join(dev_skill_dir, "evals", "evals.json")

    if not os.path.exists(evals_file):
        return f"测试失败：未找到 {evals_file}"

    try:
        with open(evals_file, "r", encoding="utf-8") as f:
            evals_data = json.load(f)
    except json.JSONDecodeError:
        return "测试失败：evals.json 格式错误，无法解析为有效的 JSON。"

    cases = evals_data.get("evals", [])
    if not cases:
        return "测试报告：evals.json 中没有任何测试用例。"

    if new_iteration:
        # 手动「运行评测」：强制新开一代，Trigger 与盲测同属这一代
        iteration_dir, iteration_idx = _get_next_iteration_dir(workplace_root)
        os.makedirs(iteration_dir, exist_ok=True)
        _run_trigger_evals(workplace_id, skill_name, iteration_dir)
    else:
        # 盲测与最近一轮 Trigger 测试共用同一迭代目录
        iteration_dir, iteration_idx = _get_eval_iteration_dir(workplace_root)
        os.makedirs(iteration_dir, exist_ok=True)

    # 启动错位并发任务池
    async def spawn_tasks():
        tasks = []
        for case in cases:
            # 创建独立协程扔进事件循环
            task_coro = asyncio.create_task(
                _run_single_eval_case(
                    case,
                    dev_skill_dir,
                    iteration_dir,
                    workplace_id,
                    skill_name,
                    iteration_idx,
                )
            )
            tasks.append(task_coro)
            # 发布间隔错位 3 秒
            await asyncio.sleep(3)

        # 等待所有错位任务执行完毕并聚合并发结果
        return await asyncio.gather(*tasks)

    results = await spawn_tasks()

    benchmark_cases, run_summary = _aggregate_results(results)
    benchmark_data = {"run_summary": run_summary, "cases": benchmark_cases}

    benchmark_path = os.path.join(iteration_dir, "benchmark.json")
    with open(benchmark_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, ensure_ascii=False, indent=2)

    pass_count = sum(1 for c in benchmark_cases if c["pass"])
    _write_json(
        os.path.join(iteration_dir, "eval_result.json"),
        {
            "skill_name": skill_name,
            "iteration": iteration_idx,
            "generated_at": _now_iso(),
            "total": len(benchmark_cases),
            "passed": pass_count,
            "summary": run_summary["with_skill"],
            "cases": benchmark_cases,
        },
    )
    render_skill_report(workplace_root, iteration_dir, iteration_idx, skill_name)

    token_mean = run_summary["with_skill"]["tokens"]["mean"]
    return (
        f"📊 盲测通过 {pass_count}/{len(benchmark_cases)}，"
        f"平均 {run_summary['with_skill']['time_seconds']['mean']}s / {token_mean} tokens，"
        f"报告已生成（iteration-{iteration_idx}/report.html）。"
    )

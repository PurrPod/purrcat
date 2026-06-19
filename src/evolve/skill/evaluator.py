"""
Skill 测试执行器 (evolve/skill/evaluator.py)
利用底层 Harness 原生双 Agent 工作流完成隔离环境下的盲测与自评。
已升级为【错位并发】模式：多测试用例隔离并行，极大缩短评测耗时。
"""

import os
import json
import shutil
import asyncio
import threading
import re
import math
from src.harness.process import Task


def run_skill_eval_background(workplace_id: str, skill_name: str, main_session_id: str):
    """启动后台线程跑自动化流水线"""

    def _bg_task():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            report = loop.run_until_complete(_async_run_evals(workplace_id, skill_name))
            from src.agent.manager import manager

            manager.agent_force_push(
                f"🔔 【测试结果】技能 '{skill_name}' 的自动化沙盒盲测已完成！\n\n{report}",
                type="system",
            )
        except Exception as e:
            from src.agent.manager import manager

            manager.agent_force_push(
                f"❌ 技能 '{skill_name}' (工作区: {workplace_id}) 的后台测试运行崩溃: {e}",
                type="system",
            )
        finally:
            loop.close()

    threading.Thread(
        target=_bg_task, daemon=True, name=f"EvalRunner_{workplace_id}"
    ).start()


def _get_next_iteration_dir(workplace_root: str) -> tuple[str, int]:
    max_idx = 0
    if os.path.exists(workplace_root):
        for item in os.listdir(workplace_root):
            match = re.match(r"iteration-(\d+)", item)
            if match:
                idx = int(match.group(1))
                if idx > max_idx:
                    max_idx = idx
    next_idx = max_idx + 1
    return os.path.join(workplace_root, f"iteration-{next_idx}"), next_idx


def _calculate_stats(values: list[float]) -> dict:
    if not values:
        return {"mean": 0.0, "stddev": 0.0}
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    stddev = math.sqrt(variance)
    return {"mean": round(mean, 2), "stddev": round(stddev, 2)}


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


# 🌟 核心拆分 1：单例测试运行器协程
async def _run_single_eval_case(
    case, dev_skill_dir, iteration_dir, workplace_id, skill_name, iteration_idx
):
    try:
        case_id = case.get("id", "unknown")
        eval_run_dir = os.path.join(iteration_dir, f"eval-{case_id}", "with_skill")
        sandbox_eval_dir = f"/agent_vm/skill_workplace/{workplace_id}/iteration-{iteration_idx}/eval-{case_id}/with_skill"

        def ignore_eval_files(dir_path, contents):
            return ["evals", "README.md", ".git", ".gitignore", "__pycache__"]

        shutil.copytree(dev_skill_dir, eval_run_dir, ignore=ignore_eval_files)
        outputs_dir = os.path.join(eval_run_dir, "outputs")
        os.makedirs(outputs_dir, exist_ok=True)

        if "files" in case:
            for file_path in case["files"]:
                src_file = os.path.join(dev_skill_dir, file_path)
                if os.path.exists(src_file):
                    dst_file = os.path.join(eval_run_dir, os.path.basename(file_path))
                    shutil.copy2(src_file, dst_file)

        prompt = case.get("prompt", "")
        expected = case.get("expected_output", "")
        assertions = case.get("assertions", [])
        qa_expected = (
            f"【预期结果】\n{expected}\n\n【硬性断言检查清单(Assertions)】\n"
            + "\n".join([f"- {a}" for a in assertions])
        )

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

        if res.get("status") == "success":
            outputs = res.get("outputs", {})
            eval_res = outputs.get("eval_result", {})
            if isinstance(eval_res, str):
                try:
                    eval_res = json.loads(eval_res)
                except Exception:
                    eval_res = {}

            is_pass = eval_res.get("pass", False)
            reason = eval_res.get("reason", "未提供理由")
            grading_data = eval_res.get("grading_data", {})

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

        pass_str = "✅ 通过 (PASS)" if is_pass else "❌ 失败 (FAIL)"
        report_str = (
            f"### 用例: {case_id}\n"
            f"- **状态**: {pass_str}\n"
            f"- **耗时**: {elapsed:.2f}s | **Tokens**: {tokens}\n"
            f"- **裁判评估**: {reason}\n"
            f"- **行为轨迹**: 测试工人轨迹已生成在：{trace_filepath}\n\n"
        )

        return benchmark_item, report_str, elapsed, tokens

    except Exception as e:
        return (
            {
                "case_id": case.get("id", "unknown"),
                "pass": False,
                "time_seconds": 0,
                "tokens": 0,
                "reason": f"框架崩溃: {str(e)}",
            },
            f"### 用例: {case.get('id', 'unknown')}\n- 崩溃: {str(e)}\n\n",
            0.0,
            0,
        )


async def _async_run_evals(workplace_id: str, skill_name: str) -> str:
    workplace_root = f"./agent_vm/skill_workplace/{workplace_id}"
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

    iteration_dir, iteration_idx = _get_next_iteration_dir(workplace_root)
    os.makedirs(iteration_dir, exist_ok=True)

    # 🌟 核心拆分 2：启动错位并发任务池
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
            # ✨ “看人下菜碟”：发布间隔错位 3 秒
            await asyncio.sleep(3)

        # 等待所有错位任务执行完毕并聚合并发结果
        return await asyncio.gather(*tasks)

    # 启动全量并发收集！
    results = await spawn_tasks()

    report_lines = [
        f"# {skill_name} 自动化盲测与基准报告 (Iteration {iteration_idx})\n"
    ]
    benchmark_cases = []
    total_time, total_tokens = 0.0, 0

    # 将并发获取的结果按顺序拼装回报告
    for benchmark_item, report_str, elapsed, tokens in results:
        benchmark_cases.append(benchmark_item)
        report_lines.append(report_str)
        total_time += elapsed
        total_tokens += tokens

    pass_values = [1.0 if c["pass"] else 0.0 for c in benchmark_cases]
    time_values = [c["time_seconds"] for c in benchmark_cases]
    token_values = [c["tokens"] for c in benchmark_cases]

    benchmark_data = {
        "run_summary": {
            "with_skill": {
                "pass_rate": _calculate_stats(pass_values),
                "time_seconds": _calculate_stats(time_values),
                "tokens": _calculate_stats(token_values),
            }
        },
        "cases": benchmark_cases,
    }

    benchmark_path = os.path.join(iteration_dir, "benchmark.json")
    with open(benchmark_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, ensure_ascii=False, indent=2)

    pass_count = sum(1 for c in benchmark_cases if c["pass"])
    report_lines.append(f"## 📊 全局基准统计 (Benchmark - Iteration {iteration_idx})")
    report_lines.append(f"- **总通过率**: {pass_count}/{len(benchmark_cases)}")
    report_lines.append(
        f"- **平均通过率**: {benchmark_data['run_summary']['with_skill']['pass_rate']['mean'] * 100:.1f}%"
    )
    report_lines.append(
        f"- **平均耗时**: {benchmark_data['run_summary']['with_skill']['time_seconds']['mean']}s (标准差: {benchmark_data['run_summary']['with_skill']['time_seconds']['stddev']}s)"
    )
    report_lines.append(
        f"- **平均 Tokens**: {benchmark_data['run_summary']['with_skill']['tokens']['mean']} (标准差: {benchmark_data['run_summary']['with_skill']['tokens']['stddev']})"
    )

    final_report = "\n".join(report_lines)
    with open(
        os.path.join(iteration_dir, "eval_report.md"), "w", encoding="utf-8"
    ) as f:
        f.write(final_report)

    return final_report

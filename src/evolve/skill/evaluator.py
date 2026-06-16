"""
Skill 测试执行器 (evolve/skill/evaluator.py)
利用底层 Harness 原生双 Agent 工作流完成隔离环境下的盲测与自评。
完全对齐 agentskills.io 官方评测标准，支持递增多版本迭代存档与全向指标统计。
"""
import os
import json
import shutil
import asyncio
import threading
import re
import math
from src.harness.process import Task


def _get_next_iteration_dir(workplace_root: str) -> tuple[str, int]:
    """
    扫描工作区，自动计算并获取下一次迭代的目录路径与序号 (iteration-N)
    """
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
    """
    计算一组数据的均值 (mean) 与标准差 (stddev)
    """
    if not values:
        return {"mean": 0.0, "stddev": 0.0}
    
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    stddev = math.sqrt(variance)
    
    return {
        "mean": round(mean, 2),
        "stddev": round(stddev, 2)
    }


def run_skill_eval_background(workplace_id: str, skill_name: str, main_session_id: str):
    """启动后台线程跑自动化流水线"""
    def _bg_task():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            report = loop.run_until_complete(_async_run_evals(workplace_id, skill_name))
            from src.agent.manager import manager
            manager.agent_force_push(f"🔔 【测试结果】技能 '{skill_name}' 的自动化沙盒盲测已完成！\n\n{report}", type="system")
        except Exception as e:
            from src.agent.manager import manager
            manager.agent_force_push(f"❌ 技能 '{skill_name}' (工作区: {workplace_id}) 的后台测试运行崩溃: {e}", type="system")
        finally:
            loop.close()
    
    threading.Thread(target=_bg_task, daemon=True, name=f"EvalRunner_{workplace_id}").start()


def _format_and_save_trace(memory_path: str, output_trace_path: str):
    """
    清洗 Agent 运行轨迹并格式化为结构化 Markdown
    """
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
                        # 提取 content 和 reasoning_content
                        content = msg.get("content", "")
                        reasoning = msg.get("reasoning_content", "")
                        
                        a_text = ""
                        if reasoning:
                            a_text += f"{reasoning}\n"
                        if content:
                            a_text += f"{content}"
                            
                        if a_text.strip():
                            trace_lines.append(f"\n[A]{a_text.strip()}")
                        
                        # 提取工具调用名
                        tool_calls = msg.get("tool_calls", [])
                        for tc in tool_calls:
                            func_name = tc.get("function", {}).get("name", "unknown_tool")
                            trace_lines.append(f"\n[C]{func_name}")
                            
                    elif role == "tool":
                        raw_content = msg.get("content", "")
                        snip = ""
                        try:
                            # 解析由 _format_result 和 route.py 包装的 JSON
                            parsed = json.loads(raw_content)
                            if isinstance(parsed, dict):
                                if "metadata" in parsed and "snip" in parsed["metadata"]:
                                    snip = parsed["metadata"]["snip"]
                                elif "summary" in parsed:
                                    # 兼容 task_done 的输出
                                    snip = str(parsed["summary"])
                                else:
                                    snip = raw_content[:100] + "..."
                            else:
                                snip = raw_content[:100] + "..."
                        except json.JSONDecodeError:
                            # 兜底截断
                            snip = raw_content[:100] + "..."
                            
                        # 如果没有 snip 信息，给个默认提示
                        snip = snip if snip else "执行成功 (无简述)"
                        trace_lines.append(f"\n[R]{snip}")
                        
        except Exception as e:
            trace_lines.append(f"\n[Error] 解析轨迹失败: {str(e)}")
    else:
        trace_lines.append("\n[Error] 未找到测试工人的记忆文件")

    # 写入目标文件
    with open(output_trace_path, "w", encoding="utf-8") as out_f:
        out_f.write("\n".join(trace_lines))


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

    # 🌟 1. 提取沙盒中的 SKILL.md 信息，用于影子注入
    from src.utils.skill_helper import _parse_skill_md
    from src.tool.search.skill_search import SkillSearcher
    
    sandbox_skill_md = os.path.join(dev_skill_dir, "SKILL.md")
    sandbox_skill_data = {"name": skill_name, "description": "", "content": ""}
    if os.path.exists(sandbox_skill_md):
        parsed = _parse_skill_md(sandbox_skill_md)
        sandbox_skill_data["name"] = parsed["metadata"].get("name", skill_name)
        sandbox_skill_data["description"] = parsed["metadata"].get("description", "")
        sandbox_skill_data["content"] = parsed.get("content", "")

    # 🌟 2. 运行 Description 激发测试 (Trigger Eval)
    triggers = evals_data.get("triggers", [])
    trigger_report_lines = []
    trigger_benchmark = []
    trigger_pass_count = 0
    
    if triggers:
        searcher = SkillSearcher()
        trigger_report_lines.append(f"## 🎯 描述激发测试 (Trigger Evals)")
        
        for t in triggers:
            query = t.get("query", "")
            should_trigger = t.get("should_trigger", True)
            
            # 调用影子注入测试
            res = searcher.simulate_trigger(query, sandbox_skill_data, top_k=3, threshold=0.3)
            
            is_triggered = res["is_triggered"]
            passed = (is_triggered == should_trigger)
            if passed:
                trigger_pass_count += 1
                
            status_icon = "✅ Pass" if passed else "❌ Fail"
            behavior = "触发" if is_triggered else "未触发"
            expected = "应触发" if should_trigger else "不应触发"
            
            trigger_report_lines.append(
                f"- **{status_icon}** | 得分: {res['score']:.2f} | 实际: **{behavior}** (预期: {expected})\n"
                f"  - Query: `{query}`\n"
                f"  - 排名: {res['rank'] if res['rank']>0 else '未上榜 Top3'} | 竞争者: {res['competitors']}"
            )
            
            trigger_benchmark.append({
                "query": query,
                "should_trigger": should_trigger,
                "is_triggered": is_triggered,
                "score": res["score"],
                "passed": passed
            })
        
        trigger_report_lines.append(f"\n**激发测试通过率**: {trigger_pass_count}/{len(triggers)}\n---\n")

    # 🌟 核心重构：动态计算递增迭代存档目录，避免历史记录被抹除
    iteration_dir, iteration_idx = _get_next_iteration_dir(workplace_root)
    os.makedirs(iteration_dir, exist_ok=True)

    report_lines = [f"# {skill_name} 自动化盲测与基准报告 (Iteration {iteration_idx})\n"]
    
    # 将触发测试报告插入到报告开头
    report_lines.extend(trigger_report_lines)
    
    benchmark_cases = []
    total_time, total_tokens = 0.0, 0

    for case in cases:
        case_id = case.get("id", "unknown")
        
        # 1. 创建隔离的测试执行区 (防数据泄露)
        # 格式: iteration-latest/eval-<case_id>/with_skill/
        eval_run_dir = os.path.join(iteration_dir, f"eval-{case_id}", "with_skill")
        # 转换物理路径为沙盒容器内标准路径
        sandbox_eval_dir = f"/agent_vm/skill_workplace/{workplace_id}/iteration-{iteration_idx}/eval-{case_id}/with_skill"
        
        # 过滤掉 evals 目录和 README，防止测试 Agent 偷看断言作弊
        def ignore_eval_files(dir_path, contents):
            return ['evals', 'README.md', '.git', '.gitignore', '__pycache__']
            
        shutil.copytree(dev_skill_dir, eval_run_dir, ignore=ignore_eval_files)
        
        # 创建 outputs 目录
        outputs_dir = os.path.join(eval_run_dir, "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        
        # 拷贝测试所需的 files
        if "files" in case:
            for file_path in case["files"]:
                src_file = os.path.join(dev_skill_dir, file_path)
                if os.path.exists(src_file):
                    dst_file = os.path.join(eval_run_dir, os.path.basename(file_path))
                    shutil.copy2(src_file, dst_file)

        prompt = case.get("prompt", "")
        expected = case.get("expected_output", "")
        assertions = case.get("assertions", [])
        
        # 组装给 QA 裁判的断言清单
        qa_expected = f"【预期结果】\n{expected}\n\n【硬性断言检查清单(Assertions)】\n" + "\n".join([f"- {a}" for a in assertions])

        host_skill_md_path = os.path.abspath(os.path.join(eval_run_dir, "SKILL.md"))

        task = Task(
            task_name=f"Eval_{skill_name}_{case_id}",
            inputs={
                "host_skill_md_path": host_skill_md_path, 
                "workplace_dir": sandbox_eval_dir,  # 约束大模型的隔离目录
                "prompt": prompt,
                "expected_output": qa_expected  # 仅传递给裁判节点
            },
            graph_name="skill_eval",
            task_id=f"eval_{workplace_id}_{case_id}"
        )
        
        res = await task.run()
        
        elapsed = task.execution_time
        tokens = task.total_tokens
        total_time += elapsed
        total_tokens += tokens

        # ======== 新增：轨迹清洗与落盘 ========
        # nd_agent_exec 是 skill_eval.json 中负责干活的 Agent 节点 ID
        agent_memory_path = os.path.join(task.checkpoint_dir, "nodes", "nd_agent_exec", "memory.jsonl")
        trace_filepath = os.path.join(eval_run_dir, "trace.md")
        _format_and_save_trace(agent_memory_path, trace_filepath)
        # ====================================

        # 生成 timing.json
        timing_data = {
            "total_tokens": tokens,
            "duration_ms": int(elapsed * 1000)
        }
        with open(os.path.join(eval_run_dir, "timing.json"), "w") as f:
            json.dump(timing_data, f, indent=2)

        is_pass = False
        reason = "未知错误"
        exec_sum = "无总结"
        
        if res.get("status") == "success":
            outputs = res.get("outputs", {})
            eval_res_str = outputs.get("eval_result", "{}")
            exec_sum = outputs.get("exec_summary", "无总结")
            try:
                eval_res = json.loads(eval_res_str) if isinstance(eval_res_str, str) else eval_res_str
                is_pass = eval_res.get("pass", False)
                reason = eval_res.get("reason", "裁判员未提供具体理由")
                
                # 提取 Python Runner 生成的 grading_data，直接写入 grading.json
                grading_data = eval_res.get("grading_data", {})
                # 兼容旧版结构，确保有 summary 字段
                if "summary" not in grading_data:
                    grading_data["summary"] = {}
                grading_data["summary"]["exec_summary"] = exec_sum
            except Exception:
                reason = str(eval_res_str)
                grading_data = {"summary": {"exec_summary": exec_sum}}

            # 直接使用 grading_data 写入，完美对齐官方规范
            with open(os.path.join(eval_run_dir, "grading.json"), "w", encoding="utf-8") as f:
                json.dump(grading_data, f, ensure_ascii=False, indent=2)
        else:
            # 执行失败时也生成 grading.json
            grading_data = {
                "summary": {
                    "passed": False,
                    "reason": res.get('message', '未知错误'),
                    "exec_summary": "执行异常中断"
                }
            }
            with open(os.path.join(eval_run_dir, "grading.json"), "w", encoding="utf-8") as f:
                json.dump(grading_data, f, ensure_ascii=False, indent=2)
            reason = res.get('message', '未知错误')

        # 记录 Benchmark 数据
        benchmark_cases.append({
            "case_id": case_id,
            "pass": is_pass,
            "time_seconds": round(elapsed, 2),
            "tokens": tokens,
            "reason": reason
        })
        
        pass_str = "✅ 通过 (PASS)" if is_pass else "❌ 失败 (FAIL)"
        report_lines.append(f"### 用例: {case_id}")
        report_lines.append(f"- **状态**: {pass_str}")
        report_lines.append(f"- **耗时**: {elapsed:.2f}s | **Tokens**: {tokens}")
        report_lines.append(f"- **裁判评估**: {reason}")
        report_lines.append(f"- **行为轨迹**: 测试工人轨迹已生成在：{trace_filepath}\n")

        # 清理Docker资源
        try:
            from src.tool.bash import close_session
            await asyncio.to_thread(close_session, task.task_id)
        except Exception:
            pass

    # 🌟 核心重构：聚合当前迭代的数据指标（计算 mean 与 stddev），完美承袭官方 benchmark.json 规范
    pass_values = [1.0 if c["pass"] else 0.0 for c in benchmark_cases]
    time_values = [c["time_seconds"] for c in benchmark_cases]
    token_values = [c["tokens"] for c in benchmark_cases]

    benchmark_data = {
        "trigger_summary": {
            "pass_rate": trigger_pass_count / len(triggers) if triggers else 0,
            "cases": trigger_benchmark
        },
        "run_summary": {
            "with_skill": {
                "pass_rate": _calculate_stats(pass_values),
                "time_seconds": _calculate_stats(time_values),
                "tokens": _calculate_stats(token_values)
            }
        },
        "cases": benchmark_cases
    }
    
    with open(os.path.join(iteration_dir, "benchmark.json"), "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, ensure_ascii=False, indent=2)

    pass_count = sum(1 for c in benchmark_cases if c["pass"])
    report_lines.append(f"## 📊 全局基准统计 (Benchmark - Iteration {iteration_idx})")
    report_lines.append(f"- **总通过率**: {pass_count}/{len(benchmark_cases)}")
    report_lines.append(f"- **平均通过率**: {benchmark_data['run_summary']['with_skill']['pass_rate']['mean'] * 100:.1f}%")
    report_lines.append(f"- **平均耗时**: {benchmark_data['run_summary']['with_skill']['time_seconds']['mean']}s (标准差: {benchmark_data['run_summary']['with_skill']['time_seconds']['stddev']}s)")
    report_lines.append(f"- **平均 Tokens**: {benchmark_data['run_summary']['with_skill']['tokens']['mean']} (标准差: {benchmark_data['run_summary']['with_skill']['tokens']['stddev']})")

    final_report = "\n".join(report_lines)
    with open(os.path.join(iteration_dir, "eval_report.md"), "w", encoding="utf-8") as f:
        f.write(final_report)
        
    return final_report

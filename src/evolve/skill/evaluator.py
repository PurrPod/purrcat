"""
Skill 测试执行器 (evolve/skill/evaluator.py)
利用底层 Harness 原生双 Agent 工作流完成隔离环境下的盲测与自评。
完全对齐 agentskills.io 官方评测标准。
"""
import os
import json
import shutil
import asyncio
import threading
from src.harness.process import Task


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
    if not cases:
        return "测试报告：evals.json 中没有任何测试用例。"

    # 官方推荐的工作区记录目录
    iteration_dir = os.path.join(workplace_root, "iteration-latest")
    shutil.rmtree(iteration_dir, ignore_errors=True)
    os.makedirs(iteration_dir, exist_ok=True)

    report_lines = [f"# {skill_name} 自动化盲测与基准报告\n"]
    benchmark_cases = []
    total_time, total_tokens = 0.0, 0

    for case in cases:
        case_id = case.get("id", "unknown")
        
        # 1. 创建隔离的测试执行区 (防数据泄露)
        # 格式: iteration-latest/eval-<case_id>/with_skill/
        eval_run_dir = os.path.join(iteration_dir, f"eval-{case_id}", "with_skill")
        sandbox_eval_dir = f"/agent_vm/skill_workplace/{workplace_id}/iteration-latest/eval-{case_id}/with_skill"
        
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
            except Exception:
                reason = str(eval_res_str)

            # 生成 grading.json (简化版，由 QA 裁判统一输出 reason)
            grading_data = {
                "summary": {
                    "passed": is_pass,
                    "reason": reason,
                    "exec_summary": exec_sum
                }
            }
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

    # 汇总生成官方推荐的 benchmark.json
    pass_count = sum(1 for c in benchmark_cases if c["pass"])
    benchmark_data = {
        "run_summary": {
            "with_skill": {
                "pass_rate": pass_count / len(benchmark_cases) if benchmark_cases else 0,
                "time_seconds_total": round(total_time, 2),
                "tokens_total": total_tokens
            }
        },
        "cases": benchmark_cases
    }
    
    with open(os.path.join(iteration_dir, "benchmark.json"), "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, ensure_ascii=False, indent=2)

    report_lines.append(f"## 📊 全局基准统计 (Benchmark)")
    report_lines.append(f"- **总通过率**: {pass_count}/{len(benchmark_cases)}")
    report_lines.append(f"- **总耗时**: {total_time:.2f}s")
    report_lines.append(f"- **总 Tokens**: {total_tokens}")

    final_report = "\n".join(report_lines)
    with open(os.path.join(iteration_dir, "eval_report.md"), "w", encoding="utf-8") as f:
        f.write(final_report)
        
    return final_report

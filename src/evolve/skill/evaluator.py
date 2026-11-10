"""
Skill 测试执行器 (evolve/skill/evaluator.py)

利用底层 Harness 原生双 Agent 工作流完成隔离环境下的盲测与自评。
执行编排（Trigger / 单用例并发 / 聚合）在 runner.py，报告组装在 report.py；
本模块保留后台线程入口与 trace2skill 的来源会话快照。
"""

import asyncio
import os
import threading

from src.utils.config import AGENT_VM_DIR

from src.evolve.common.report import (
    now_iso as _now_iso,
    write_json as _write_json,
)
from src.evolve.skill.runner import (
    _aggregate_results as _runner_aggregate_results,
    _async_run_evals,
    _run_trigger_evals,
)


def run_skill_eval_background(
    workplace_id: str,
    skill_name: str,
    main_session_id: str,
    new_iteration: bool = False,
):
    """启动后台线程跑自动化流水线

    new_iteration=True（极简 UI 手动点「运行评测」）：强制新开一代，Trigger 与盲测一并跑进这一代；
    False（请求审批链路）：复用 Trigger 那一代，保持 trigger + 盲测同属一份报告。
    """

    def _bg_task():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            report = loop.run_until_complete(
                _async_run_evals(workplace_id, skill_name, new_iteration)
            )
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


def run_skill_trigger_eval_background(workplace_id: str, skill_name: str):
    """启动后台线程跑 Trigger 激发测试（无需审批，提交即运行）"""

    def _bg_task():
        try:
            report = _run_trigger_evals(workplace_id, skill_name)
            from src.agent.manager import manager

            manager.agent_force_push(
                f"🎯 【Trigger 测试结果】技能 '{skill_name}' 的激发路由测试已完成！\n\n{report}",
                type="system",
            )
        except Exception as e:
            from src.agent.manager import manager

            manager.agent_force_push(
                f"❌ 技能 '{skill_name}' (工作区: {workplace_id}) 的 trigger 测试运行崩溃: {e}",
                type="system",
            )

    threading.Thread(
        target=_bg_task, daemon=True, name=f"TriggerEval_{workplace_id}"
    ).start()


def _aggregate_results(results: list) -> tuple:
    """兼容旧入口；聚合逻辑见 runner._aggregate_results。"""
    return _runner_aggregate_results(results)


def record_trace_meta(workplace_id: str, session_id: str) -> dict:
    """trace2skill 专用：把来源会话的累计 Token 快照写入沙盒 trace_meta.json。

    该快照即「无技能时的参照成本」，后台盲测完成后由报告与盲测均值对比，
    图标化展示这个技能让后台盲测任务少花了多少 token。
    """
    workplace_root = os.path.join(AGENT_VM_DIR, "skill_workplace", workplace_id)
    if not workplace_id or not session_id or not os.path.isdir(workplace_root):
        return {}

    data = {
        "session_id": session_id,
        "source": "trace2skill",
        "recorded_at": _now_iso(),
        "consumed_total": 0,
        "consumed_main": 0,
        "consumed_sub": 0,
        "window_token": 0,
        "max_token": 0,
    }
    try:
        from src.agent.session_store import SessionStore

        consumed = SessionStore.get_session_consumed_tokens(session_id) or {}
        data["consumed_total"] = int(consumed.get("total") or 0)
        data["consumed_main"] = int(consumed.get("main") or 0)
        data["consumed_sub"] = int(consumed.get("sub") or 0)
        data["window_token"] = int(
            SessionStore.get_session_window_token(session_id) or 0
        )
    except Exception:
        return {}
    try:
        from src.agent import get_agent_max_token

        data["max_token"] = int(get_agent_max_token() or 0)
    except Exception:
        pass

    _write_json(os.path.join(workplace_root, "trace_meta.json"), data)
    return data

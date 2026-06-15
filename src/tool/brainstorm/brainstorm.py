import os
import asyncio
from pathlib import Path
from src.tool.utils.format import text_response, error_response
from src.agent.sub_runner import (
    ACTIVE_SUB_TASKS,
    SUB_TASK_LOCK,
    run_dag_graph,
    ensure_sub_loop,
)
from src.utils.config import get_file_config


def _has_write_permission(target_path: str) -> bool:
    """
    BrainStorm 内部专属的轻量级写权限校验器，避免引入 filesystem 导致循环导入。
    核心逻辑与底层文件系统保持一致。
    """
    # 1. 路径映射：将沙盒路径转换为宿主机实际路径
    path = str(target_path).strip()
    if path.startswith("/agent_vm/"):
        path = "./agent_vm/" + path[len("/agent_vm/") :]
    elif path == "/agent_vm":
        path = "./agent_vm"

    target_norm = os.path.normcase(os.path.abspath(path))
    target_path_obj = Path(target_norm)

    # 2. 读取系统的文件权限配置
    config = get_file_config()
    perms = config.get("permissions", {})

    best_match_len = -1
    best_perm = config.get("default_permission", "readonly")

    # 3. 匹配算法：支持绝对路径和通配符
    for perm_type in ["blocked", "readonly", "writable"]:
        for rule in perms.get(perm_type, []):
            rule_norm = os.path.normcase(rule)
            is_match = False

            if os.path.isabs(rule_norm):
                try:
                    if os.path.commonpath([target_norm, rule_norm]) == rule_norm:
                        is_match = True
                except ValueError:
                    pass

            if not is_match:
                for current_node in [target_path_obj] + list(target_path_obj.parents):
                    if current_node.match(rule_norm):
                        is_match = True
                        break

            if is_match:
                match_weight = len(rule_norm)
                if rule_norm == target_norm:
                    match_weight += 10000  # 绝对精准匹配权重最高
                if match_weight > best_match_len:
                    best_match_len = match_weight
                    best_perm = perm_type

    return best_perm == "writable"


def BrainStorm(
    action: str,
    main_plan: list = None,
    sub_branches: list = None,
    target_branch_id: str = None,
    _tool_call_id: str = None,
    **kwargs,
) -> str:
    try:
        # 🚫 核心拦截：打工仔分支没有决策和裁员权限
        if kwargs.get("_is_sub_branch"):
            return error_response(
                "越权被拒：后台子分支无权调用 BrainStorm 工具进行递归派发或强制取消操作！"
            )

        if action == "cancel":
            if not target_branch_id:
                return error_response("参数错误：缺少 target_branch_id")

            with SUB_TASK_LOCK:
                task_handle = ACTIVE_SUB_TASKS.get(target_branch_id)

            if task_handle:
                task_handle.cancel()
                return text_response(
                    f"✅ 斩杀信号已成功下发！后台分支 `{target_branch_id}` 已被强制终止。",
                    "🛑 分支已终止",
                )
            else:
                return error_response(
                    f"未在系统中捕捉到活跃运行的后台分支 `{target_branch_id}`。"
                )

        elif action == "create":
            # 🌟 新增：事前独立校验多文件的写入权限
            if sub_branches:
                for branch in sub_branches:
                    deliverables = branch.get("deliverable", [])
                    if not isinstance(deliverables, list):
                        return error_response(
                            f"参数错误：分支 `{branch.get('branch_id')}` 的 deliverable 必须是文件路径数组(array)。"
                        )

                    for target_file in deliverables:
                        if not _has_write_permission(target_file):
                            return error_response(
                                f"✋ 派发失败：分支 `{branch.get('branch_id')}` 的交付物路径 `{target_file}` 缺乏写入权限。\n"
                                f"安全策略拦截：系统拒绝派发此任务。请先调用 Request 工具为该路径申请 file_write 权限，或修改目标路径为沙盒内(/agent_vm)路径。"
                            )

            msg_lines = ["🚀 [系统] 脑暴大纲与任务排期已成功落盘生效！"]

            if main_plan:
                msg_lines.append("\n### 📌 【主干 Main 分支后续执行大纲】")
                for i, step in enumerate(main_plan, 1):
                    msg_lines.append(f"**Step {i}**. {step}")

            if sub_branches:
                msg_lines.append(
                    f"\n后台支线任务 ({len(sub_branches)}个) 已成功递交底层引擎，在暗中开辟独立线程快马加鞭运转中。"
                )

            msg_lines.append(
                "\n💡 指示：工具已闭环，你不需要进行任何循环查询。请立即按照你刚才定下的 Main 主线计划第一步去沙盒开展工作。子任务结果出来后系统会自动通知。"
            )
            final_response_text = "\n".join(msg_lines)

            if sub_branches:
                from src.agent.manager import AgentManager

                manager = AgentManager()
                main_session_id = manager.get_active_session_id()
                main_history = manager._agent.get_history()

                tool_call_id = None
                if main_history and len(main_history) > 0:
                    last_msg = main_history[-1]
                    if last_msg.get("role") == "assistant" and last_msg.get(
                        "tool_calls"
                    ):
                        tool_call_id = last_msg["tool_calls"][0]["id"]

                if tool_call_id:
                    sub_tool_result_msg = {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": "BrainStorm",
                        "content": text_response(
                            final_response_text, "🚀 脑暴计划已生效"
                        ),
                    }
                    main_history.append(sub_tool_result_msg)

                loop = ensure_sub_loop()
                asyncio.run_coroutine_threadsafe(
                    run_dag_graph(sub_branches, main_session_id, main_history),
                    loop,
                )

            return text_response(final_response_text, "🚀 脑暴计划已生效")

        return error_response("无效的 action 指令")

    except Exception as e:
        return error_response(f"BrainStorm 调度引擎崩溃: {e}")

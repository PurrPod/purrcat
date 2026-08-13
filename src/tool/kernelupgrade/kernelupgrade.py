"""KernelUpgrade 工具主入口 - 实时执行无需审批"""

import os
import traceback
from src.tool.utils.format import error_response, text_response
from src.utils.config import SKILL_DIR
from src.evolve import (
    skill_improve_init,
    run_skill_eval_background,
    mcp_improve_init,
    mcp_upgrade_init,
    run_mcp_eval_background,
)


def KernelUpgrade(action: str, target: str, **kwargs) -> dict:
    """
    Agent 的自我进化内核升级工具。
    - action="trace_to_skill": 将轨迹沉淀为技能（自动判断新建或升级）
    - action="test_skill": 在后台运行 Skill 沙盒盲测
    - action="create_mcp": 生成全新的 MCP Server 骨架
    - action="upgrade_mcp": 拷贝现存的 MCP Server 进行修改
    - action="test_mcp": 在后台运行 MCP 并发测试
    """
    try:
        if action == "trace_to_skill":
            is_upgrade = os.path.exists(os.path.join(SKILL_DIR, target))

            sys_note = skill_improve_init(target, is_upgrade=is_upgrade)

            status_str = "已" if is_upgrade else "未"
            action_str = "安排升级" if is_upgrade else "创建"

            return text_response(
                f"{status_str}检测到skill:{target}，已为你{action_str}工厂。\n\n{sys_note}",
                f"🎉 {target} 进化沙盒已就绪",
            )

        elif action == "test_skill":
            parts = target.split("/")
            if len(parts) != 2:
                return error_response(
                    f"执行失败：target 格式不正确，应为 'uuid/skill_name'。当前输入为: '{target}'",
                    "❌ 路径格式错误",
                )

            workplace_id, skill_name = parts

            from src.agent.manager import manager

            main_session_id = manager.get_active_session_id()

            # 🌟 捕获返回的 task_id
            task_id = run_skill_eval_background(
                workplace_id, skill_name, main_session_id
            )
            task_id_info = f" (Task ID: {task_id})" if isinstance(task_id, str) else ""

            msg = (
                f"🚀 技能 '{skill_name}' 的自动化盲测流水线已在后台启动！{task_id_info}\n"
                f"💡 提示：你可以使用 `Task` 工具查询测试状态或注入追加指令。\n"
                f"测试通常需要 30 秒至几分钟，完成后将自动通过系统级通知向你汇报测试结果。⚠️ 禁止频繁轮询测试结果浪费资源，请挂起等待或做其他工作！"
            )
            return text_response(msg, f"⏳ {skill_name} 盲测运行中")

        elif action == "create_mcp":
            sys_note = mcp_improve_init(target)
            return text_response(
                f"✅ 全新 MCP Server 沙盒构建完成！\n\n{sys_note}",
                f"🔌 {target} MCP已创建",
            )

        elif action == "upgrade_mcp":
            sys_note = mcp_upgrade_init(target)
            return text_response(
                f"✅ 现存 MCP Server 已拷贝至进化沙盒，准备好进行升级！\n\n{sys_note}",
                f"📦 {target} MCP沙盒已就绪",
            )

        elif action == "test_mcp":
            parts = target.split("/")
            if len(parts) != 2:
                return error_response(
                    f"执行失败：target 格式不正确，应为 'uuid/mcp_name'。当前输入为: '{target}'",
                    "❌ 路径格式错误",
                )

            workplace_id, mcp_name = parts

            # ==========================================
            # 🌟 新增：前置强拦截（防 Agent 偷懒跳步）
            # ==========================================
            schema_path = f"./agent_vm/mcp_workplace/{workplace_id}/{mcp_name}/evals/outputs/schema_dump.json"
            if not os.path.exists(schema_path):
                return error_response(
                    "❌ 执行被拒绝：未检测到测试前置产物！\n\n"
                    "由于当前 MCP 还处于沙盒开发期，你必须先亲自在沙盒里测试scripts/evaluation.py能否跑通！\n"
                    "只有当上述脚本成功执行，并生成了 `evals/outputs/schema_dump.json` 之后，你才有资格调用 `test_mcp`！",
                    "❌ 缺失前置产物",
                )

            # 只有通过了检查，才允许往下走启动后台任务
            from src.agent.manager import manager

            main_session_id = manager.get_active_session_id()

            # 🌟 捕获返回的 task_id
            task_id = run_mcp_eval_background(workplace_id, mcp_name, main_session_id)
            task_id_info = f" (Task ID: {task_id})" if isinstance(task_id, str) else ""

            msg = (
                f"🚀 MCP '{mcp_name}' 的并发测试流水线已在后台启动！{task_id_info}\n"
                f"💡 提示：你可以使用 `Task` 工具查询状态或挂起当前任务等待系统级通知。\n"
            )
            return text_response(msg, f"⏳ {mcp_name} 宿主机评测中")

        else:
            return error_response(
                f"不支持的 action: {action}。当前系统暂未实装该模块的进化能力，请检查拼写或等待后续版本升级。",
                "❌ 参数/不支持的操作",
            )

    except Exception as e:
        traceback.print_exc()
        return error_response(f"KernelUpgrade 执行异常: {str(e)}", "❌ 执行失败")

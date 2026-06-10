import asyncio
from src.tool.utils.format import text_response, error_response
from src.agent.sub_runner import ACTIVE_SUB_TASKS, SUB_TASK_LOCK, run_dag_graph

def BrainStorm(action: str, main_plan: list = None, sub_branches: list = None, target_branch_id: str = None, **kwargs) -> str:
    try:
        # 🚫 权限拦截：子分支绝对不允许调用 BrainStorm
        if kwargs.get("_is_sub_branch"):
            return error_response("权限不足：后台子分支不允许调用 BrainStorm 工具进行递归派发或干预！")

        if action == "cancel":
            if not target_branch_id:
                return error_response("参数错误：缺少 target_branch_id")
            
            with SUB_TASK_LOCK:
                task_handle = ACTIVE_SUB_TASKS.get(target_branch_id)
            
            if task_handle:
                task_handle.cancel()
                return text_response({"status": "success"}, f"✅ 斩杀指令已下发！子分支 `{target_branch_id}` 已被强制终止。")
            else:
                return error_response(f"未检测到运行中的子分支 `{target_branch_id}`，其可能已自动结束。")

        elif action == "create":
            # 将 plan 作为工具调用的返回值输出，保持严丝合缝的 ToolCall 闭环
            msg_lines = []
            msg_lines.append("🚀 [系统] 脑暴计划已全面落盘生效！")
            
            if main_plan:
                msg_lines.append("\n### 📌 【Main 主线执行计划】")
                for i, step in enumerate(main_plan, 1):
                    msg_lines.append(f"**Step {i}**. {step}")
            
            if sub_branches:
                from src.agent.manager import AgentManager
                manager = AgentManager()
                main_session_id = manager.get_active_session_id()
                main_history = manager.get_chat_history()
                
                # 丢给 asyncio 事件循环跑后台任务
                loop = asyncio.get_running_loop()
                loop.create_task(run_dag_graph(sub_branches, main_session_id, main_history))
                
                msg_lines.append(f"\n后台并发支线 ({len(sub_branches)}个) 已在暗中全速运转。完成后会自动通知你。")

            msg_lines.append("\n💡 指示：无需挂起等待！请立刻顺着上述 Main 计划去开展工作。")

            return text_response({"status": "success"}, "\n".join(msg_lines))

        return error_response("无效的 action 指令")
        
    except Exception as e:
        return error_response(f"BrainStorm 引擎崩溃: {e}")
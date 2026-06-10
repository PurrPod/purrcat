import asyncio
import json
from src.tool.utils.format import text_response, error_response
from src.agent.sub_runner import ACTIVE_SUB_TASKS, SUB_TASK_LOCK, run_dag_graph, ensure_sub_loop

def BrainStorm(action: str, main_plan: list = None, sub_branches: list = None, target_branch_id: str = None, _tool_call_id: str = None, **kwargs) -> str:
    try:
        # 🚫 核心拦截：打工仔分支没有决策和裁员权限
        if kwargs.get("_is_sub_branch"):
            return error_response("越权被拒：后台子分支无权调用 BrainStorm 工具进行递归派发或强制取消操作！")

        if action == "cancel":
            if not target_branch_id:
                return error_response("参数错误：缺少 target_branch_id")
            
            with SUB_TASK_LOCK:
                task_handle = ACTIVE_SUB_TASKS.get(target_branch_id)
            
            if task_handle:
                task_handle.cancel()
                return text_response({"status": "success"}, f"✅ 斩杀信号已成功下发！后台分支 `{target_branch_id}` 已被强制终止。")
            else:
                return error_response(f"未在系统中捕捉到活跃运行的后台分支 `{target_branch_id}`。")

        elif action == "create":
            msg_lines = ["🚀 [系统] 脑暴大纲与任务排期已成功落盘生效！"]
            
            if main_plan:
                msg_lines.append("\n### 📌 【主干 Main 分支后续执行大纲】")
                for i, step in enumerate(main_plan, 1):
                    msg_lines.append(f"**Step {i}**. {step}")
            
            tool_result_text = "\n".join(msg_lines)
            
            if sub_branches:
                from src.agent.manager import AgentManager
                manager = AgentManager()
                main_session_id = manager.get_active_session_id()
                
                # 获取当前主分支历史（此时已包含工具调用记录在 [-1]）
                # 🌟 修复：绕过 manager.get_chat_history() 的 system 过滤，直接获取底层全量记录
                # 这样 sub 分支能复用主分支的 KV Cache，实现 100% 前缀树命中
                main_history = manager._agent.get_history()
                
                # 🌟 从历史最后一条获取真正的 tool_call_id
                tool_call_id = None
                if main_history and len(main_history) > 0:
                    last_msg = main_history[-1]
                    if last_msg.get("role") == "assistant" and last_msg.get("tool_calls"):
                        tool_call_id = last_msg["tool_calls"][0]["id"]
                
                # 🌟 核心修复：这个 main_history 是马上要传给 sub 线程当初始历史用的。
                # 给它塞入一个专属的 Tool 成功响应，而主干的响应是通过底部的 return 自动完成的。
                if tool_call_id:
                    sub_tool_result_msg = {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": "BrainStorm",
                        "content": text_response({"status": "success"}, "✅ 脑暴生成成功，当前已被分配到 sub 分支。")
                    }
                    main_history.append(sub_tool_result_msg)
                
                loop = ensure_sub_loop()
                asyncio.run_coroutine_threadsafe(
                    # 这里传过去的 main_history 就已经闭环了，和主干完全不串味
                    run_dag_graph(sub_branches, main_session_id, main_history), 
                    loop
                )
                
                msg_lines.append(f"\n后台支线任务 ({len(sub_branches)}个) 已成功递交底层引擎，在暗中开辟独立线程快马加鞭运转中。")

            msg_lines.append("\n💡 指示：工具已闭环，你不需要进行任何循环查询。请立即按照你刚才定下的 Main 主线计划第一步去沙盒开展工作。子任务结果出来后系统会自动通知。")

            return text_response({"status": "success"}, "\n".join(msg_lines))

        return error_response("无效的 action 指令")
        
    except Exception as e:
        return error_response(f"BrainStorm 调度引擎崩溃: {e}")

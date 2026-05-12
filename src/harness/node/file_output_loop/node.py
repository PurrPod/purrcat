import os
import json
from typing import Dict, Any
from src.harness.node.base import BaseNode
from src.harness.utils.llm_helper import call_llm, inject_force_push
from src.harness.utils.tool_helper import get_system_schema, extract_tool_calling, check_tool_call_completed


class Node(BaseNode):
    """文件输出循环节点：封装思考->调用工具->验收的完整循环逻辑"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        tools = get_system_schema()
        
        original_file_path = inputs.get("file_path") or self.config.get("file_path") or f"{context.workplace}/FINISHED.md"
        
        check_file_path = original_file_path
        if check_file_path.startswith("/agent_vm/"):
            check_file_path = check_file_path[1:]
            
        check_file_path = os.path.abspath(os.path.join(os.getcwd(), check_file_path))
        agent_vm_dir = os.path.abspath(os.path.join(os.getcwd(), "agent_vm"))
        in_sandbox = os.path.commonpath([check_file_path, agent_vm_dir]) == agent_vm_dir

        if force_push_msgs:
            messages = inject_force_push(messages, force_push_msgs)

        step = 0
        max_steps = 500

        while step < max_steps:
            step += 1
            try:
                dynamic_push = []
                with context._lock:
                    if self.node_id in context.pending_force_push:
                        dynamic_push = context.pending_force_push.pop(self.node_id)
                if dynamic_push:
                    self.log(context, "SYSTEM", f"🔔 检测到实时人工干预，已注入 {len(dynamic_push)} 条指令")
                    messages = inject_force_push(messages, dynamic_push)

                response, messages = await call_llm(
                    model=context.model,
                    messages=messages,
                    tools=tools,
                    node_log_func=self.log,
                    context=context
                )

                tool_calls = extract_tool_calling(response)

                if not tool_calls:
                    messages.append({"role": "user", "content": "检测到你没有调用任何工具，如已完成任务，请调用 task_done 总结该阶段任务"})
                    continue

                # 🚨 修正：使用基类的工具路由分发方法
                tool_messages = self.execute_tool_calling(tool_calls, context)
                if tool_messages:
                    messages.extend(tool_messages)

                if check_tool_call_completed(tool_calls):
                    if self._check_file_exist(check_file_path):
                        display_path = f"/agent_vm/{original_file_path}" if in_sandbox else original_file_path
                        messages.append({"role": "user", "content": f"✅ 检测到你调用了 task_done，目标文件 {display_path} 已成功生成，任务完成！"})
                        summary = "任务完成"
                        for tc in tool_calls:
                            if tc.function.name == "task_done":
                                try:
                                    args = json.loads(tc.function.arguments)
                                    summary = args.get("summary", summary)
                                except:
                                    pass
                        return {
                            "messages": messages,
                            "summary": summary
                        }
                    else:
                        if in_sandbox:
                            display_path = f"/agent_vm/{original_file_path}" if not original_file_path.startswith("/agent_vm") else original_file_path
                            error_msg = f"未检测到沙盒文件：{display_path}"
                        else:
                            error_msg = f"未检测到本地文件：{original_file_path}"
                        
                        full_msg = f"{error_msg}。请检查是否生成在了其他路径，并及时生成目标文件。如果你实在无法完成任务，请使用yield_to_human工具直接挂起任务，这是被允许的！"
                        messages.append({"role": "user", "content": full_msg})
                        continue

            except Exception as e:
                self.log(context, "ERROR", f"❌ 运行发生异常: {e}")
                raise

        if step >= max_steps:
            raise TimeoutError(f"节点执行超出最大思考步数 ({max_steps})，被强制中断。")

        last_msg = messages[-1]["content"] if messages else "任务完成"
        return {"messages": messages, "summary": last_msg}

    def _check_file_exist(self, file_path: str) -> bool:
        return os.path.exists(file_path)

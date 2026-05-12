import json
from typing import Dict, Any
from src.harness.node.base import BaseNode
from src.harness.utils.llm_helper import call_llm, inject_force_push
from src.harness.utils.tool_helper import get_system_schema, extract_tool_calling, check_tool_call_completed


class Node(BaseNode):
    """总结输出循环节点：封装思考->调用工具->总结的完整循环逻辑"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        tools = get_system_schema()

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

                assistant_msg = response.choices[0].message
                tool_calls = extract_tool_calling(response)

                if not tool_calls:
                    messages.append({"role": "user", "content": "检测到你没有调用任何工具，如已完成任务，请调用 task_done 总结该阶段任务"})
                    continue

                # 🚨 修正：使用基类的工具路由分发方法
                tool_messages = self.execute_tool_calling(tool_calls, context)
                if tool_messages:
                    messages.extend(tool_messages)

                if check_tool_call_completed(tool_calls):
                    summary = assistant_msg.content or "任务完成"
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

            except Exception as e:
                self.log(context, "ERROR", f"❌ 运行发生异常: {e}")
                raise

        if step >= max_steps:
            raise TimeoutError(f"节点执行超出最大思考步数 ({max_steps})，被强制中断。")

        return {
            "messages": messages,
            "summary": "任务完成"
        }

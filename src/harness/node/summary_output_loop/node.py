import json
import asyncio
from typing import Dict, Any
from src.harness.node.base import BaseNode
from src.harness.utils.llm_helper import call_llm, inject_force_push
from src.harness.utils.tool_helper import get_system_schema, extract_tool_calling, check_tool_call_completed


class Node(BaseNode):
    """总结输出循环节点：封装思考->调用工具->总结的完整循环逻辑"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        tools = get_system_schema()

        # 初始的外部 force_push
        if force_push_msgs:
            messages = inject_force_push(messages, force_push_msgs)

        step = 0
        max_steps = 500

        try:
            while step < max_steps:
                # 🌟 1. 每时每刻检查自身是否还是 RUNNING 状态
                if not self.check_running_state(context):
                    self.log(context, "SYSTEM", "⚠️ 节点状态已变更，退出当前执行循环。")
                    raise asyncio.CancelledError()

                # 🌟 2. 安全的注入时机：循环开头！此时前置工具一定已经执行完毕。
                dynamic_push = self.consume_pending_messages(context)
                if dynamic_push:
                    self.log(context, "SYSTEM", f"🔔 检测到新指令/级联影响，注入 {len(dynamic_push)} 条消息")
                    messages = inject_force_push(messages, dynamic_push)

                # 3. 正常调用大模型
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
                    step += 1
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

                step += 1

        except asyncio.CancelledError:
            self.log(context, "SYSTEM", "🛑 节点执行被外部强行打断！")
            raise

        except Exception as e:
            self.log(context, "ERROR", f"❌ 运行发生异常: {e}")
            raise

        if step >= max_steps:
            raise TimeoutError(f"节点执行超出最大思考步数 ({max_steps})，被强制中断。")

        return {
            "messages": messages,
            "summary": "任务完成"
        }

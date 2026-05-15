import os
import json
import asyncio
from typing import Dict, Any
from src.harness.node.base import BaseNode
from src.harness.utils.llm_helper import call_llm, inject_force_push
from src.harness.utils.tool_helper import get_system_schema, extract_tool_calling
from src.harness.enums import LogType, NodeState


class Node(BaseNode):
    """文件输出循环节点：封装思考->调用工具->验收的完整循环逻辑"""

    async def execute(
        self, inputs: Dict[str, Any], force_push_msgs: list, context: Any
    ) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        tools = get_system_schema()

        original_file_path = inputs.get("file_path") or self.config.get("file_path")

        # 必须以 /agent_vm 开头，否则报错
        if not original_file_path or not original_file_path.startswith("/agent_vm"):
            raise ValueError(
                f"文件路径必须以'/agent_vm'开头，当前输入: {original_file_path}"
            )

        # 移除 /agent_vm/ 前缀以获取相对路径
        check_file_path = (
            original_file_path[len("/agent_vm/") :]
            if original_file_path.startswith("/agent_vm/")
            else original_file_path[len("/agent_vm") :]
        )
        check_file_path = os.path.abspath(
            os.path.join(os.getcwd(), "agent_vm", check_file_path)
        )

        # 初始的外部 force_push
        if force_push_msgs:
            messages = inject_force_push(messages, force_push_msgs)

        step = 0
        max_steps = 500

        try:
            while step < max_steps:
                step += 1
                self.log(
                    context,
                    LogType.SYSTEM,
                    f"🔄 [循环步骤] 第 {step}/{max_steps} 步，上下文消息数: {len(messages)}，目标文件: {original_file_path}",
                )

                # 🌟 1. 每时每刻检查自身是否还是 RUNNING 状态
                if not self.check_running_state(context):
                    self.log(
                        context,
                        LogType.SYSTEM,
                        "⚠️ [循环退出] 节点状态已变更为非 running",
                    )
                    raise asyncio.CancelledError()

                # 🌟 2. 安全的注入时机：循环开头！此时前置工具一定已经执行完毕。
                dynamic_push = self.consume_pending_messages(context)
                if dynamic_push:
                    self.log(
                        context,
                        LogType.SYSTEM,
                        f"🔔 [指令注入] 检测到 {len(dynamic_push)} 条人类/级联干预",
                    )
                    for idx, msg in enumerate(dynamic_push, 1):
                        preview = msg[:50] + "..." if len(msg) > 50 else msg
                        self.log(
                            context, LogType.SYSTEM, f"   └─ 注入内容 {idx}: {preview}"
                        )
                    messages = inject_force_push(messages, dynamic_push)

                # 3. 正常调用大模型
                self.log(context, LogType.SYSTEM, "🧠 [LLM调用] 正在请求大模型...")
                response, messages = await call_llm(
                    model=context.model, messages=messages, tools=tools
                )

                assistant_msg = response.choices[0].message
                tool_calls = extract_tool_calling(response)

                # 记录模型思考内容
                if assistant_msg.content:
                    thought_preview = (
                        assistant_msg.content[:100] + "..."
                        if len(assistant_msg.content) > 100
                        else assistant_msg.content
                    )
                    self.log(
                        context, LogType.SYSTEM, f"💭 [模型思考] {thought_preview}"
                    )

                # 记录工具调用
                if tool_calls:
                    self.log(
                        context,
                        LogType.SYSTEM,
                        f"🔧 [工具调用] 检测到 {len(tool_calls)} 个工具调用",
                    )
                    for tc in tool_calls:
                        args_preview = (
                            tc.function.arguments[:80] + "..."
                            if len(tc.function.arguments) > 80
                            else tc.function.arguments
                        )
                        self.log(
                            context,
                            LogType.SYSTEM,
                            f"   └─ {tc.function.name}({args_preview})",
                        )
                else:
                    self.log(
                        context, LogType.SYSTEM, "⚠️ [无工具调用] 模型未调用任何工具"
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": "检测到你没有调用任何工具，如已完成任务，请调用 task_done 总结该阶段任务",
                        }
                    )
                    continue

                # 🚨 修正：使用基类的工具路由分发方法
                tool_messages = self.execute_tool_calling(tool_calls, context)
                if tool_messages:
                    self.log(
                        context,
                        LogType.SYSTEM,
                        f"📦 [工具返回] 收到 {len(tool_messages)} 个工具执行结果",
                    )
                    messages.extend(tool_messages)

                # 🌟 处理 yield_to_human 挂起逻辑
                is_yield = any(
                    tc.function.name == "yield_to_human" for tc in tool_calls
                )
                if is_yield:
                    self.log(
                        context, LogType.SYSTEM, "⏸️ [节点挂起] 正在阻塞等待人类干预..."
                    )
                    context.node_state[self.node_id] = NodeState.WAITING  # 修改节点状态

                    # [新增] 主动给 Agent 发送弹窗通知
                    try:
                        from src.agent.manager import get_agent

                        agent = get_agent()
                        if agent:
                            agent.force_push(
                                f"⚠️ 子任务 [{context.task_name}] (ID: {context.task_id}) 的节点 [{self.node_id}] 正在等待进一步指令，已挂起。请对症下药，使用 Task 工具的 submit_request 向该节点注入指令！",
                                type="task_message",
                            )
                    except Exception as e:
                        self.log(context, LogType.ERROR, f"通知 Agent 失败: {e}")

                    # 真正的阻塞！只有等来了人类输入才跳出循环
                    while True:
                        await asyncio.sleep(2)  # 释放 CPU
                        # 检查是否被强制终止
                        if not self.check_running_state(context):
                            self.log(
                                context,
                                LogType.SYSTEM,
                                "⚠️ [循环退出] 节点状态已变更为非 running",
                            )
                            raise asyncio.CancelledError()
                        dynamic_push = self.consume_pending_messages(context)
                        if dynamic_push:
                            self.log(
                                context,
                                LogType.SYSTEM,
                                "▶️ [节点恢复] 收到指令，唤醒执行",
                            )
                            messages = inject_force_push(messages, dynamic_push)
                            context.node_state[self.node_id] = NodeState.RUNNING
                            break
                    continue  # 带着人类的新指令，进入下一轮 LLM 对话

                # 🌟 限定在 task_done 上才进行任务完成校验
                is_done = any(tc.function.name == "task_done" for tc in tool_calls)
                if is_done:
                    if self._check_file_exist(check_file_path):
                        self.log(
                            context,
                            LogType.SYSTEM,
                            f"✅ [文件验证] 目标文件已存在: {original_file_path}",
                        )
                        messages.append(
                            {
                                "role": "user",
                                "content": f"✅ 检测到你调用了 task_done，目标文件 {original_file_path} 已成功生成，任务完成！",
                            }
                        )
                        summary = assistant_msg.content or "任务完成"
                        for tc in tool_calls:
                            if tc.function.name == "task_done":
                                try:
                                    args = json.loads(tc.function.arguments)
                                    summary = args.get("summary", summary)
                                except Exception:
                                    pass
                        self.log(
                            context,
                            LogType.SYSTEM,
                            f"✅ [任务完成] 总结: {summary[:100]}..."
                            if len(summary) > 100
                            else f"✅ [任务完成] 总结: {summary}",
                        )
                        return {"messages": messages, "summary": summary}
                    else:
                        self.log(
                            context,
                            LogType.SYSTEM,
                            f"⚠️ [文件缺失] 目标文件未生成: {original_file_path}，要求重新生成",
                        )
                        full_msg = f"未检测到沙盒文件：{original_file_path}。请检查是否生成在了其他路径，并及时生成目标文件。如果你实在无法完成任务，请使用yield_to_human工具直接挂起任务，这是被允许的！"
                        messages.append({"role": "user", "content": full_msg})
                        continue

        except asyncio.CancelledError:
            self.log(context, LogType.SYSTEM, "🛑 [节点中断] 引擎强行打断当前协程")
            raise

        except Exception as e:
            self.log(context, LogType.ERROR, f"❌ [循环异常] {e}")
            raise

        if step >= max_steps:
            raise TimeoutError(f"节点执行超出最大思考步数 ({max_steps})，被强制中断。")

        last_msg = messages[-1]["content"] if messages else "任务完成"
        return {"messages": messages, "summary": last_msg}

    def _check_file_exist(self, file_path: str) -> bool:
        return os.path.exists(file_path)

import asyncio
import json
import os
from typing import Any, Dict

from src.harness.enums import LogType, NodeState
from src.harness.node.base import BaseNode
from src.harness.utils.llm_helper import call_llm, inject_force_push
from src.harness.utils.tool_helper import extract_tool_calling


class Node(BaseNode):
    """文件输出循环节点：封装思考->调用工具->验收的完整循环逻辑"""

    async def execute(
        self, inputs: Dict[str, Any], force_push_msgs: list, context: Any
    ) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        tools = self.get_all_tools()

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

        # 计算沙盒根目录
        sandbox_root = os.path.abspath(os.path.join(os.getcwd(), "agent_vm"))
        check_file_path = os.path.abspath(os.path.join(sandbox_root, check_file_path.lstrip("/")))

        # 【新增安全校验】防止路径穿越攻击
        if not check_file_path.startswith(sandbox_root):
            raise ValueError(f"安全警告: 文件路径存在越权访问风险 {original_file_path}")

        # 初始的外部 force_push
        if force_push_msgs:
            messages = inject_force_push(messages, force_push_msgs)

        step = 0
        max_steps = 500

        # 连续错误计数器 - 用于熔断机制
        consecutive_no_tool_errors = 0
        consecutive_file_missing_errors = 0
        MAX_CONSECUTIVE_ERRORS = 3  # 连续错误阈值

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
                    consecutive_no_tool_errors += 1
                    consecutive_file_missing_errors = 0  # 重置另一类错误计数

                    if consecutive_no_tool_errors >= MAX_CONSECUTIVE_ERRORS:
                        self.log(
                            context,
                            LogType.SYSTEM,
                            f"🔴 [熔断触发] 连续 {MAX_CONSECUTIVE_ERRORS} 次未调用工具，强制挂起求助人类",
                        )
                        # 强制挂起并通知用户
                        context.node_state[self.node_id] = NodeState.WAITING
                        try:
                            from src.agent.manager import get_agent

                            agent = get_agent()
                            if agent:
                                agent.force_push(
                                    f"🔴 子任务 [{context.task_name}] (ID: {context.task_id}) 的节点 [{self.node_id}] 触发熔断：连续 {MAX_CONSECUTIVE_ERRORS} 次未调用工具，任务陷入死循环，请人工介入！",
                                    type="task_message",
                                )
                        except Exception as e:
                            self.log(context, LogType.ERROR, f"通知 Agent 失败: {e}")

                        # 等待人类干预
                        while True:
                            await asyncio.sleep(2)
                            if not self.check_running_state(context):
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
                                consecutive_no_tool_errors = 0  # 重置计数器
                                break
                        continue

                    self.log(
                        context, LogType.SYSTEM, f"⚠️ [无工具调用] 模型未调用任何工具 (连续 {consecutive_no_tool_errors}/{MAX_CONSECUTIVE_ERRORS})"
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": "检测到你没有调用任何工具，如已完成任务，请调用 task_done 总结该阶段任务",
                        }
                    )
                    continue

                # 🚨 享受重构红利：直接把 response 丢给基类分发器
                tool_messages, is_task_done, is_yield = await self.execute_tool_calling(response, context)
                if tool_messages:
                    self.log(
                        context,
                        LogType.SYSTEM,
                        f"📦 [工具返回] 收到 {len(tool_messages)} 个工具执行结果",
                    )
                    messages.extend(tool_messages)

                # 🌟 处理 yield_to_human 挂起阻塞
                if is_yield:
                    self.log(
                        context, LogType.SYSTEM, "⏸️ [节点挂起] 正在阻塞等待人类干预..."
                    )

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

                    # 🌟 听你的，直接拿到新消息，不传历史列表进去了
                    new_human_msgs = await self.wait_for_human_intervention(context)
                    messages.extend(new_human_msgs)
                    
                    continue

                # 🌟 验证任务完成
                if is_task_done:
                    if self._check_file_exist(check_file_path):
                        self.log(
                            context,
                            LogType.SYSTEM,
                            f"✅ [文件验证] 目标文件已存在: {original_file_path}",
                        )

                        # 解析 task_done 传来的字典
                        final_summary = {}
                        for tc in tool_calls:
                            if tc.function.name == "task_done":
                                try:
                                    args = json.loads(tc.function.arguments)
                                    final_summary = args.get("summary", {})
                                except Exception:
                                    pass

                        # 🌟 最爽的一步：节点完美落盘
                        final_outputs = {"messages": messages, "summary": final_summary}
                        self.save_checkpoints(context, {"inputs": inputs, "outputs": final_outputs})

                        return final_outputs
                    else:
                        consecutive_file_missing_errors += 1
                        consecutive_no_tool_errors = 0  # 重置另一类错误计数

                        if consecutive_file_missing_errors >= MAX_CONSECUTIVE_ERRORS:
                            self.log(
                                context,
                                LogType.SYSTEM,
                                f"🔴 [熔断触发] 连续 {MAX_CONSECUTIVE_ERRORS} 次文件生成失败，强制挂起求助人类",
                            )
                            # 强制挂起并通知用户
                            context.node_state[self.node_id] = NodeState.WAITING
                            try:
                                from src.agent.manager import get_agent

                                agent = get_agent()
                                if agent:
                                    agent.force_push(
                                        f"🔴 子任务 [{context.task_name}] (ID: {context.task_id}) 的节点 [{self.node_id}] 触发熔断：连续 {MAX_CONSECUTIVE_ERRORS} 次文件生成失败，请人工介入！",
                                        type="task_message",
                                    )
                            except Exception as e:
                                self.log(context, LogType.ERROR, f"通知 Agent 失败: {e}")

                            # 等待人类干预
                            while True:
                                await asyncio.sleep(2)
                                if not self.check_running_state(context):
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
                                    consecutive_file_missing_errors = 0  # 重置计数器
                                    break
                            continue

                        self.log(
                            context,
                            LogType.SYSTEM,
                            f"⚠️ [文件缺失] 目标文件未生成: {original_file_path}，要求重新生成 (连续 {consecutive_file_missing_errors}/{MAX_CONSECUTIVE_ERRORS})",
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

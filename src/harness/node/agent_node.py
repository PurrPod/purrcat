import asyncio
import json
import os
from typing import Any, Dict, List

from src.harness.enums import LogType, NodeState
from src.harness.node.base import BaseNode, _format_result
from src.harness.utils.llm_helper import call_llm
from src.harness.utils.tool_helper import execute_global_tool, extract_tool_calling


class AgentNode(BaseNode):
    """
    专门处理 LLM 对话、工具调用、大循环控制以及人类干预的节点基类

    🌟 新架构特性：节点自治数据管理
    - 每个节点拥有自己的专属文件夹：nodes/node_id/
    - 对话历史使用 JSONL 格式追加写入（memory.jsonl）
    - 大文件存放在 artifacts/ 子目录
    """

    # 标识该节点支持接受外部指令注入，用于 Dashboard 过滤
    can_inject = True

    WORKFLOW_CORE_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "task_done",
                "description": "标记当前阶段任务完成。必须在此刻对成果进行全面总结。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "object",
                            "description": "对当前阶段的结构化总结数据（请严格按照系统要求的 JSON 键值对格式输出）",
                        }
                    },
                    "required": ["summary"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "yield_to_human",
                "description": "将控制权交还给人类，请求人工干预或确认",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "需要人类干预的原因",
                        }
                    },
                    "required": ["reason"],
                },
            },
        },
    ]

    def get_memory_file_path(self, context) -> str:
        """获取该节点的记忆文件路径：nodes/node_id/memory.jsonl"""
        node_dir = os.path.join(context.checkpoint_dir, "nodes", self.node_id)
        os.makedirs(node_dir, exist_ok=True)
        return os.path.join(node_dir, "memory.jsonl")

    def _sync_dump_memory(self, context, messages: List[Dict]):
        """实时写盘小助手，保证执行期间前端能实时探班气泡"""
        node_dir = os.path.join(context.checkpoint_dir, "nodes", self.node_id)
        os.makedirs(node_dir, exist_ok=True)
        # 写到 live_memory.json，与 API 接口的优先级 2 完美对齐
        out_file = os.path.join(node_dir, "live_memory.json")
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False)
        except Exception:
            pass

    def get_artifacts_dir(self, context) -> str:
        """获取该节点的大文件存放目录：nodes/node_id/artifacts/"""
        artifacts_dir = os.path.join(
            context.checkpoint_dir, "nodes", self.node_id, "artifacts"
        )
        os.makedirs(artifacts_dir, exist_ok=True)
        return artifacts_dir

    def load_memory_from_file(self, context) -> List[Dict]:
        """从 JSONL 文件加载对话历史（追加写入格式）"""
        memory_path = self.get_memory_file_path(context)
        messages = []

        if os.path.exists(memory_path):
            try:
                with open(memory_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            messages.append(json.loads(line))
            except Exception as e:
                self.log(context, "WARNING", f"⚠️ [记忆加载失败] {e}")

        return messages

    def append_memory_to_file(self, context, new_messages: List[Dict]):
        """追加写入新消息到 JSONL 文件（O(1) 复杂度）"""
        memory_path = self.get_memory_file_path(context)

        try:
            with open(memory_path, "a", encoding="utf-8") as f:
                for msg in new_messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        except Exception as e:
            self.log(context, "WARNING", f"⚠️ [记忆追加失败] {e}")

    def clear_memory_file(self, context):
        """清空节点的记忆文件（用于重置）"""
        memory_path = self.get_memory_file_path(context)
        if os.path.exists(memory_path):
            os.remove(memory_path)

    def get_all_tools(self) -> List[dict]:
        from src.harness.utils.tool_helper import get_system_schema

        tools = get_system_schema()
        tools.extend(self.WORKFLOW_CORE_TOOLS)
        return tools

    def migrate_old_memory(self, old_memory: dict, context):
        """将旧格式的 node_memory 迁移到新的 JSONL 格式"""
        messages = old_memory.get("messages", [])
        if messages:
            self.append_memory_to_file(context, messages)

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """
        🌟 新架构入口：节点自治管理记忆
        - 从自己的 memory.jsonl 文件读取历史（按行读，速度极快）
        - 每次收到新消息立即追加写入（O(1) 复杂度）
        - 只向引擎返回精简的 summary 和文件指针
        """

        dynamic_info = inputs.get("task_done_info")
        if dynamic_info:
            try:
                if isinstance(dynamic_info, str):
                    self.task_done_info = json.loads(dynamic_info)
                elif isinstance(dynamic_info, dict):
                    self.task_done_info = dynamic_info
                self.log(
                    context,
                    "SYSTEM",
                    f"✅ [动态规则挂载] 成功加载动态校验指标: {list(self.task_done_info.keys())}",
                )
            except Exception as e:
                self.log(
                    context,
                    "WARNING",
                    f"⚠️ [动态规则挂载] 解析失败，将不使用强校验: {e}",
                )

        # 🌟 获取当前节点专属的记忆文件路径
        mem_path = self.get_memory_file_path(context)

        # 1. 从自己的专属文件读取历史记忆 (按行读，速度极快)
        messages = []
        if os.path.exists(mem_path):
            with open(mem_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(json.loads(line))

        # 2. 如果上游传来了新的 messages，合并进来并立刻存盘
        new_upstream_msgs = inputs.get("messages", [])
        if new_upstream_msgs:
            messages.extend(new_upstream_msgs)
            # 立刻存盘上游的新消息
            await asyncio.to_thread(
                self.append_memory_to_file, context, new_upstream_msgs
            )

        # 3. 处理强制推送的指令（通过 node_memory 传递）
        my_memory = context.node_memory.setdefault(self.node_id, {})
        pending_push = my_memory.pop("force_push", [])
        if isinstance(pending_push, list) and pending_push:
            force_push_msgs = [
                {"role": "user", "content": f"[人工指令] {msg}"} for msg in pending_push
            ]
            messages.extend(force_push_msgs)
            # 立刻存盘强制推送的指令
            await asyncio.to_thread(
                self.append_memory_to_file, context, force_push_msgs
            )

        # ========================================================
        # 🌟 新增：注入 task_done 工具使用说明与格式强校验文案 (User角色)
        # ========================================================
        task_done_prompt = (
            "【任务完结要求】\n"
            "当你认为已经完成了本阶段的核心思考和所有必要操作后，请务必调用 `task_done` 工具来标注任务已完成并移交控制权。\n"
        )

        if getattr(self, "task_done_info", None):
            task_done_prompt += "⚠️ 注意：调用 `task_done` 工具时，你的 `summary` 参数必须严格包含以下 JSON 字段及内容：\n"
            for key, desc in self.task_done_info.items():
                task_done_prompt += f'  - "{key}": {desc}\n'
        else:
            task_done_prompt += "⚠️ 注意：调用 `task_done` 工具时，请在 `summary` 参数中输出详尽的任务执行总结。\n"

        # 检查是否已经注入过该提示（防止任务挂起恢复或重跑时重复写入）
        has_injected = False
        for msg in messages[-5:]:
            if msg.get("role") == "user" and "【任务完结要求】" in msg.get(
                "content", ""
            ):
                has_injected = True
                break

        if not has_injected:
            # 修改点：这里将 role 从 system 改为了 user
            user_msg = {"role": "user", "content": task_done_prompt}
            messages.append(user_msg)
            # 立刻追加落盘，保证前端气泡也能看到这条明确的指令
            await asyncio.to_thread(self.append_memory_to_file, context, [user_msg])
        # ========================================================

        tools = self.get_all_tools()

        try:
            loop_result = await self.run_agent_loop(context, messages, tools, mem_path)

            # 🌟 彻底解耦：向引擎返回精简数据，不返回那几十兆的 messages
            return {
                "summary": loop_result["summary"],
                # 如果下游真的需要获取上游记录，可以直接传文件指针过去：
                "memory_pointer": mem_path,
            }

        except asyncio.CancelledError:
            # 取消时也保存当前状态
            await asyncio.to_thread(self.append_memory_to_file, context, messages)
            raise

    async def run_agent_loop(
        self,
        context: Any,
        messages: List[Dict],
        tools: List[Dict],
        mem_path: str = None,
        max_steps: int = 500,
    ) -> Dict[str, Any]:
        """
        🌟 新架构 Agent 大循环：每次 LLM 回复后立即追加写入
        - mem_path: 节点专属记忆文件路径
        """
        step = 0
        MAX_CONSECUTIVE_ERRORS = 3
        consecutive_no_tool_errors = 0
        consecutive_format_errors = 0
        initial_message_count = len(messages)

        while step < max_steps:
            step += 1
            self.log(
                context, LogType.SYSTEM, f"🔄 [Agent思考步] 第 {step}/{max_steps} 步"
            )

            if context.node_state.get(self.node_id) not in [
                NodeState.RUNNING,
                NodeState.WAITING,
            ]:
                self.log(context, "WARNING", "⚠️ [状态检查] 节点状态异常，终止循环")
                raise asyncio.CancelledError()

            # 🌟 新架构：从 node_memory 接收动态注入的指令
            my_memory = context.node_memory.setdefault(self.node_id, {})
            dynamic_push = my_memory.pop("force_push", [])
            if isinstance(dynamic_push, list) and dynamic_push:
                self.log(
                    context,
                    "SYSTEM",
                    f"🔔 [动态注入] 收到 {len(dynamic_push)} 条强制推送消息",
                )
                force_push_msgs = [
                    {"role": "user", "content": f"[人工指令] {msg}"}
                    for msg in dynamic_push
                ]
                messages.extend(force_push_msgs)
                # 立刻存盘
                if mem_path:
                    await asyncio.to_thread(
                        self.append_memory_to_file, context, force_push_msgs
                    )

            self.log(
                context,
                "SYSTEM",
                f"🧠 [LLM调用] 发送 {len(messages)} 条消息给大模型...",
            )
            response, messages = await call_llm(context.model, messages, tools)
            assistant_msg = response.choices[0].message

            # 🌟 关键改进：每次 LLM 回复后立即追加写入
            if mem_path:
                new_messages = messages[initial_message_count:]
                if new_messages:
                    await asyncio.to_thread(
                        self.append_memory_to_file, context, new_messages
                    )
                    # 🌟 关键修复点 1：大模型刚回复完，马上触发后台写盘，此时前端气泡弹出
                    await asyncio.to_thread(self._sync_dump_memory, context, messages)
                    initial_message_count = len(messages)

            if assistant_msg.content:
                content_preview = (
                    assistant_msg.content[:200] + "..."
                    if len(assistant_msg.content) > 200
                    else assistant_msg.content
                )
                self.log(context, "SYSTEM", f"💭 [模型回复] {content_preview}")

            tool_calls = extract_tool_calling(response)

            if not tool_calls:
                consecutive_no_tool_errors += 1
                self.log(
                    context,
                    "WARNING",
                    f"⚠️ [无工具调用] 连续 {consecutive_no_tool_errors}/{MAX_CONSECUTIVE_ERRORS} 次无工具调用",
                )
                if consecutive_no_tool_errors >= MAX_CONSECUTIVE_ERRORS:
                    self.log(
                        context, LogType.SYSTEM, "🔴 [熔断] 连续无工具调用，挂起求助"
                    )
                    context.node_state[self.node_id] = NodeState.WAITING
                    raise asyncio.CancelledError("Circuit Breaker")
                messages.append({"role": "user", "content": "请调用 task_done 工具。"})
                continue

            self.log(
                context, "SYSTEM", f"🔧 [工具调用] 检测到 {len(tool_calls)} 个工具调用"
            )
            tool_messages, is_task_done, is_yield = await self.execute_tool_calling(
                response, context
            )

            # 🌟 工具调用结果也立即写入
            if tool_messages and mem_path:
                await asyncio.to_thread(
                    self.append_memory_to_file, context, tool_messages
                )
                # 🌟 关键修复点 2：工具执行完并追加到 messages 后，再次写盘，前端显示工具结果
                await asyncio.to_thread(self._sync_dump_memory, context, messages)
                initial_message_count = len(messages) + len(tool_messages)

            if tool_messages:
                messages.extend(tool_messages)

            if tool_messages and not is_task_done and not is_yield:
                has_format_error = any(
                    tm.get("name") == "task_done" and "error" in tm.get("content", "")
                    for tm in tool_messages
                )

                if has_format_error:
                    consecutive_format_errors += 1
                    if consecutive_format_errors >= MAX_CONSECUTIVE_ERRORS:
                        self.log(
                            context,
                            LogType.SYSTEM,
                            f"🔴 [熔断] 连续 {MAX_CONSECUTIVE_ERRORS} 次未能按照要求格式输出，挂起求助",
                        )
                        context.node_state[self.node_id] = NodeState.WAITING
                        raise asyncio.CancelledError("Format Error Circuit Breaker")
                else:
                    consecutive_format_errors = 0

            if is_yield:
                self.log(context, LogType.SYSTEM, "⏸️ [节点挂起] 等待人类指令...")
                context.node_state[self.node_id] = NodeState.WAITING
                raise asyncio.CancelledError("User Intervention Required")

            if is_task_done:
                final_summary = self._extract_summary(tool_calls, assistant_msg.content)
                self.log(context, "SYSTEM", "✅ [任务完成] Agent 循环结束，返回总结")
                return {"messages": messages, "summary": final_summary}

        raise TimeoutError("超出最大思考步数")

    async def execute_tool_calling(
        self, response: Any, context: Any
    ) -> tuple[list, bool, bool]:
        """统一处理普通工具、拓展工具与工作流原语"""
        tool_calls = extract_tool_calling(response)
        tool_messages = []
        is_task_done = False
        is_yield = False

        for tc in tool_calls:
            original_tool_name = tc.function.name
            arguments_str = tc.function.arguments
            try:
                arguments = json.loads(arguments_str) if arguments_str else {}
            except json.JSONDecodeError:
                arguments = {}

            self.log(context, "SYSTEM", f"  🔧 [执行工具] {original_tool_name}")
            args_preview = json.dumps(arguments, ensure_ascii=False)[:100]
            self.log(
                context,
                "SYSTEM",
                f"     📥 参数: {args_preview}{'...' if len(json.dumps(arguments, ensure_ascii=False)) > 100 else ''}",
            )

            final_content = ""

            if original_tool_name == "task_done":
                summary = arguments.get("summary", {})
                if not isinstance(summary, dict):
                    summary = {"raw": str(summary)}

                if self.task_done_info:
                    self.log(
                        context,
                        "SYSTEM",
                        f"     🔍 [校验规则] 需要字段: {list(self.task_done_info.keys())}",
                    )
                    self.log(
                        context,
                        "SYSTEM",
                        f"     📋 [提交内容] 字段: {list(summary.keys())}",
                    )
                    missing_keys = [
                        f"'{k}' ({v})"
                        for k, v in self.task_done_info.items()
                        if k not in summary
                    ]
                    if missing_keys:
                        error_msg = f"❌ [格式错误] 你尝试完成任务，但 summary 缺失了系统强制要求的关键信息：{', '.join(missing_keys)}。"
                        self.log(
                            context,
                            "WARNING",
                            f"     ⚠️ [任务完结被拒] 缺少必填参数: {missing_keys}",
                        )
                        final_content = _format_result(
                            {
                                "error": error_msg,
                                "instruction": "请重新调用 task_done 工具，并确保 summary 参数严格包含上述提到的所有键值对！",
                                "required_schema": self.task_done_info,
                            }
                        )
                    else:
                        if context:
                            context.result = True
                        self.log(
                            context,
                            "SYSTEM",
                            f"     ✅ [校验通过] 输出合规: {json.dumps(summary, ensure_ascii=False)[:150]}",
                        )
                        final_content = _format_result(
                            {"status": "success", "summary": summary}
                        )
                        is_task_done = True
                else:
                    if context:
                        context.result = True
                    self.log(
                        context,
                        "SYSTEM",
                        f"     ✅ [无校验规则] 直接通过: {json.dumps(summary, ensure_ascii=False)[:150]}",
                    )
                    final_content = _format_result(
                        {"status": "success", "summary": summary}
                    )
                    is_task_done = True

            elif original_tool_name == "yield_to_human":
                reason = arguments.get("reason", "需要人工干预")
                self.log(context, "SYSTEM", f"⏸️ [请求干预] 理由: {reason}")
                context.node_state[self.node_id] = NodeState.WAITING
                final_content = _format_result(
                    {"status": "suspended", "message": "已挂起，等待人类注入指令"}
                )
                is_yield = True

            else:
                try:
                    self.log(
                        context,
                        LogType.TOOL_CALL,
                        f"🔧 [全局工具] {original_tool_name}",
                    )
                    arguments["_caller"] = "harness"

                    # 🟢 使用 to_thread 将工具执行放入独立的线程池，避免异步跨线程子进程死锁
                    import asyncio

                    raw_result = await asyncio.to_thread(
                        execute_global_tool,
                        original_tool_name,
                        arguments,
                        context=context,
                    )

                    final_content = _format_result(raw_result)
                    self.log(
                        context,
                        LogType.TOOL,
                        f"📦 [工具返回] {original_tool_name} -> {str(final_content)[:50]}...",
                    )
                except Exception as e:
                    final_content = _format_result(
                        {"error": f"❌ [工具崩溃] {original_tool_name}: {e}"}
                    )

            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": original_tool_name,
                    "content": final_content,
                }
            )

        return tool_messages, is_task_done, is_yield

    def _extract_summary(self, tool_calls, fallback_content):
        summary = fallback_content or "任务完成"
        for tc in tool_calls:
            if tc.function.name == "task_done":
                try:
                    summary = json.loads(tc.function.arguments).get("summary", summary)
                except Exception:
                    pass
        return summary

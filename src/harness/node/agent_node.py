import asyncio
import json
from typing import Any, Dict, List

from src.harness.enums import LogType, NodeState
from src.harness.node.base import BaseNode, _format_result
from src.harness.utils.llm_helper import call_llm, inject_force_push
from src.harness.utils.tool_helper import execute_global_tool, extract_tool_calling


class AgentNode(BaseNode):
    """
    专门处理 LLM 对话、工具调用、大循环控制以及人类干预的节点基类
    """

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
                            "description": "对当前阶段的结构化总结数据（请严格按照系统要求的 JSON 键值对格式输出）"
                        }
                    },
                    "required": ["summary"]
                }
            }
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
                            "description": "需要人类干预的原因"
                        }
                    },
                    "required": ["reason"]
                }
            }
        }
    ]

    def get_all_tools(self) -> List[dict]:
        from src.harness.utils.tool_helper import get_system_schema
        tools = get_system_schema()
        tools.extend(self.WORKFLOW_CORE_TOOLS)
        return tools

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """全新极简入口：从专属记忆空间恢复上下文"""
        
        my_memory = context.node_memory.setdefault(self.node_id, {})
        
        messages = my_memory.get("messages", inputs.get("messages", []))
        
        pending_push = my_memory.pop("force_push", [])
        if pending_push:
            for msg in pending_push:
                messages.append({"role": "user", "content": f"[人工指令] {msg}"})

        tools = self.get_all_tools()
        
        try:
            loop_result = await self.run_agent_loop(context, messages, tools)
            
            my_memory["messages"] = loop_result["messages"]
            return {"messages": loop_result["messages"], "summary": loop_result["summary"]}
            
        except asyncio.CancelledError:
            my_memory["messages"] = messages
            raise

    async def run_agent_loop(self, context: Any, messages: List[Dict], tools: List[Dict], max_steps: int = 500) -> Dict[str, Any]:
        """精简版 Agent 大循环"""
        step = 0
        MAX_CONSECUTIVE_ERRORS = 3
        consecutive_no_tool_errors = 0

        while step < max_steps:
            step += 1
            self.log(context, LogType.SYSTEM, f"🔄 [Agent思考步] 第 {step}/{max_steps} 步")

            if context.node_state.get(self.node_id) not in [NodeState.RUNNING, NodeState.WAITING]:
                raise asyncio.CancelledError()

            my_memory = context.node_memory.get(self.node_id, {})
            dynamic_push = my_memory.pop("force_push", [])
            if dynamic_push:
                messages = inject_force_push(messages, dynamic_push)

            response, messages = await call_llm(context.model, messages, tools)
            assistant_msg = response.choices[0].message
            tool_calls = extract_tool_calling(response)

            if not tool_calls:
                consecutive_no_tool_errors += 1
                if consecutive_no_tool_errors >= MAX_CONSECUTIVE_ERRORS:
                    self.log(context, LogType.SYSTEM, "🔴 [熔断] 连续无工具调用，挂起求助")
                    context.node_state[self.node_id] = NodeState.WAITING
                    raise asyncio.CancelledError("Circuit Breaker")
                messages.append({"role": "user", "content": "请调用 task_done 工具。"})
                continue

            tool_messages, is_task_done, is_yield = await self.execute_tool_calling(response, context)
            if tool_messages:
                messages.extend(tool_messages)

            if is_yield:
                self.log(context, LogType.SYSTEM, "⏸️ [节点挂起] 等待人类指令...")
                context.node_state[self.node_id] = NodeState.WAITING
                raise asyncio.CancelledError("User Intervention Required")

            if is_task_done:
                final_summary = self._extract_summary(tool_calls, assistant_msg.content)
                return {"messages": messages, "summary": final_summary}

        raise TimeoutError(f"超出最大思考步数")

    async def execute_tool_calling(self, response: Any, context: Any) -> tuple[list, bool, bool]:
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

            final_content = ""

            if original_tool_name == "task_done":
                summary = arguments.get("summary", {})
                if not isinstance(summary, dict):
                    summary = {"raw": str(summary)}

                if self.task_done_info:
                    missing_keys = [f"'{k}' ({v})" for k, v in self.task_done_info.items() if k not in summary]
                    if missing_keys:
                        error_msg = f"❌ [格式错误] 你尝试完成任务，但 summary 缺失了系统强制要求的关键信息：{', '.join(missing_keys)}。"
                        self.log(context, "WARNING", f"⚠️ [任务完结被拒] 大模型缺少必填参数: {missing_keys}")
                        final_content = _format_result({
                            "error": error_msg,
                            "instruction": "请重新调用 task_done 工具，并确保 summary 参数严格包含上述提到的所有键值对！",
                            "required_schema": self.task_done_info
                        })
                    else:
                        if context: context.result = True
                        self.log(context, "SYSTEM",
                                 f"✅ [任务完结校验通过] 输出合规: {json.dumps(summary, ensure_ascii=False)}")
                        final_content = _format_result({"status": "success", "summary": summary})
                        is_task_done = True
                else:
                    if context: context.result = True
                    self.log(context, "SYSTEM",
                             f"✅ [任务完结信号] 大模型总结: {json.dumps(summary, ensure_ascii=False)}")
                    final_content = _format_result({"status": "success", "summary": summary})
                    is_task_done = True

            elif original_tool_name == "yield_to_human":
                reason = arguments.get("reason", "需要人工干预")
                self.log(context, "SYSTEM", f"⏸️ [请求干预] 理由: {reason}")
                context.node_state[self.node_id] = NodeState.WAITING
                final_content = _format_result({"status": "suspended", "message": "已挂起，等待人类注入指令"})
                is_yield = True

            elif original_tool_name == "call_tool":
                action = arguments.get("action", "execute")
                local_registry, local_schemas = self.get_local_tools()
                if action == "list":
                    if not local_schemas:
                        msg = "当前节点暂未挂载任何拓展业务工具。"
                    else:
                        schema_list_str = json.dumps([s["function"] for s in local_schemas], ensure_ascii=False,
                                                     indent=2)
                        msg = f"当前可用的拓展业务工具有以下几种，请参考其参数格式并在下一步调用：\n{schema_list_str}"
                    final_content = _format_result({"available_tools": msg})
                elif action == "execute":
                    target_tool_name = arguments.get("tool_name")
                    target_arguments = arguments.get("tool_args", {})
                    if not target_tool_name or target_tool_name not in local_registry:
                        final_content = _format_result({"error": f"⚠️ [工具缺失] 未找到 '{target_tool_name}'"})
                    else:
                        try:
                            self.log(context, LogType.TOOL_CALL, f"🔧 [拓展工具] {target_tool_name}")
                            ToolClass = local_registry[target_tool_name]
                            raw_result = ToolClass(context=context).execute(target_arguments)
                            final_content = _format_result(raw_result)
                        except Exception as e:
                            final_content = _format_result(
                                {"error": f"❌ [工具异常] {target_tool_name} 执行失败: {str(e)}"})
            else:
                try:
                    self.log(context, LogType.TOOL_CALL, f"🔧 [全局工具] {original_tool_name}")
                    raw_result = execute_global_tool(original_tool_name, arguments, context=context)
                    final_content = _format_result(raw_result)
                    self.log(context, LogType.TOOL,
                             f"📦 [工具返回] {original_tool_name} -> {str(final_content)[:50]}...")
                except Exception as e:
                    final_content = _format_result({"error": f"❌ [工具崩溃] {original_tool_name}: {e}"})

            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": original_tool_name,
                "content": final_content,
            })

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

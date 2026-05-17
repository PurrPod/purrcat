import datetime
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import dotenv_values
import yaml

from src.harness.enums import LogType
from src.harness.utils.tool_helper import execute_global_tool, extract_tool_calling


def _format_result(result_data) -> str:
    if isinstance(result_data, str):
        try:
            parsed = json.loads(result_data)
            if "content" in parsed and "timestamp" in parsed:
                return result_data
            else:
                result_data = parsed
        except json.JSONDecodeError:
            pass

    finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(result_data, dict):
        result_data["timestamp"] = finish_time
        return json.dumps(result_data, ensure_ascii=False)

    return json.dumps(
        {"content": str(result_data), "timestamp": finish_time}, ensure_ascii=False
    )


class BaseNode:
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

    def __init__(self, node_id: str, config: dict):
        self.node_id = node_id
        self.config = config
        self.module_path = sys.modules[self.__module__].__file__
        self.node_dir = os.path.dirname(self.module_path)
        self.tools_dir = os.path.join(self.node_dir, "tools")
        self._local_tools_registry = None
        self._local_tools_schemas = None
        
        self.metadata = self._load_metadata()
        self.task_done_info = self.config.get("task_done_info", self.metadata.get("task_done_info", {}))

    def _load_metadata(self) -> dict:
        base_path = Path(self.node_dir)
        metadata = {}
        try:
            json_path = base_path / "metadata.json"
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                    if isinstance(json_data, dict):
                        metadata.update(json_data)
        except Exception as e:
            print(f"⚠️ [元数据加载警告] 节点 {self.__class__.__module__} 加载配置出错: {e}")
        return metadata

    def get_local_tools(self):
        if self._local_tools_registry is not None:
            return self._local_tools_registry, self._local_tools_schemas
        self._local_tools_registry = {}
        self._local_tools_schemas = []
        if not os.path.isdir(self.tools_dir):
            return self._local_tools_registry, self._local_tools_schemas
        try:
            for item in os.listdir(self.tools_dir):
                item_path = os.path.join(self.tools_dir, item)
                if os.path.isdir(item_path) and not item.startswith("_"):
                    meta_path = os.path.join(item_path, f"{item}.json")
                    if os.path.exists(meta_path):
                        with open(meta_path, "r", encoding="utf-8") as f:
                            schema = json.load(f)
                        tool_name = schema["function"]["name"]
                        self._local_tools_schemas.append(schema)
                        package_path = self.__module__.rsplit(".", 1)[0]
                        tool_module_path = f"{package_path}.tools.{item}.tool"
                        module = importlib.import_module(tool_module_path)
                        self._local_tools_registry[tool_name] = module.Tool
        except Exception as e:
            print(f"❌ 加载节点本地工具失败: {e}")
        return self._local_tools_registry, self._local_tools_schemas

    def get_all_tools(self) -> List[dict]:
        from src.harness.utils.tool_helper import get_system_schema
        tools = get_system_schema()
        tools.extend(self.WORKFLOW_CORE_TOOLS)
        return tools

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """由子类实现的具体执行逻辑，必须返回字典作为向外投递的包裹"""
        raise NotImplementedError

    async def execute_tool_calling(self, response: Any, context: Any) -> tuple[list, bool, bool]:
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
                    missing_keys = []
                    for req_key, req_desc in self.task_done_info.items():
                        if req_key not in summary:
                            missing_keys.append(f"'{req_key}' ({req_desc})")

                    if missing_keys:
                        error_msg = f"❌ [格式错误] 你尝试完成任务，但 summary 缺失了系统强制要求的关键信息：{', '.join(missing_keys)}。"
                        self.log(context, "WARNING", f"⚠️ [任务完结被拒] 大模型缺少必填参数: {missing_keys}")

                        final_content = _format_result({
                            "error": error_msg,
                            "instruction": "请重新调用 task_done 工具，并确保 summary 参数严格包含上述提到的所有键值对！",
                            "required_schema": self.task_done_info
                        })
                    else:
                        if context:
                            context.result = True
                        self.log(context, "SYSTEM", f"✅ [任务完结校验通过] 输出合规: {json.dumps(summary, ensure_ascii=False)}")
                        final_content = _format_result({"status": "success", "summary": summary})
                        is_task_done = True
                else:
                    if context:
                        context.result = True
                    self.log(context, "SYSTEM", f"✅ [任务完结信号] 大模型总结: {json.dumps(summary, ensure_ascii=False)}")
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
                        schema_list_str = json.dumps(
                            [s["function"] for s in local_schemas],
                            ensure_ascii=False,
                            indent=2,
                        )
                        msg = f"当前可用的拓展业务工具有以下几种，请参考其参数格式并在下一步调用：\n{schema_list_str}"

                    final_content = _format_result({"available_tools": msg})

                elif action == "execute":
                    target_tool_name = arguments.get("tool_name")
                    target_arguments = arguments.get("tool_args", {})

                    if not target_tool_name or target_tool_name not in local_registry:
                        error_msg = f"⚠️ [工具缺失] 未找到 '{target_tool_name}'"
                        self.log(context, LogType.WARNING, error_msg)
                        final_content = _format_result({"error": error_msg})
                    else:
                        try:
                            args_str = ", ".join(
                                [f"{k}={repr(v)}" for k, v in target_arguments.items()]
                            )
                            if len(args_str) > 100:
                                args_str = args_str[:97] + "..."
                            self.log(
                                context,
                                LogType.TOOL_CALL,
                                f"🔧 [拓展工具] {target_tool_name}({args_str})",
                            )

                            ToolClass = local_registry[target_tool_name]
                            tool_instance = ToolClass(context=context)
                            raw_result = tool_instance.execute(target_arguments)
                            final_content = _format_result(raw_result)

                        except Exception as e:
                            error_msg = (
                                f"❌ [工具异常] {target_tool_name} 执行失败: {str(e)}"
                            )
                            self.log(context, LogType.ERROR, error_msg)
                            final_content = _format_result({"error": error_msg})

            else:
                try:
                    args_str = ", ".join(
                        [f"{k}={repr(v)}" for k, v in arguments.items()]
                    )
                    if len(args_str) > 100:
                        args_str = args_str[:97] + "..."
                    self.log(
                        context,
                        LogType.TOOL_CALL,
                        f"🔧 [全局工具] {original_tool_name}({args_str})",
                    )

                    raw_result = execute_global_tool(
                        original_tool_name, arguments, context=context
                    )
                    final_content = _format_result(raw_result)

                    result_preview = str(final_content)[:50].replace("\n", " ")
                    self.log(
                        context,
                        LogType.TOOL,
                        f"📦 [工具返回] {original_tool_name} -> {result_preview}...",
                    )
                except Exception as e:
                    error_msg = f"❌ [工具崩溃] {original_tool_name}: {e}"
                    self.log(context, LogType.ERROR, error_msg)
                    final_content = _format_result({"error": error_msg})

            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": original_tool_name,
                "content": final_content,
            })

        return tool_messages, is_task_done, is_yield

    def log(self, context: Any, log_type: str, content: str, node_id: str = None):
        nid = node_id or self.node_id
        if hasattr(context, "log"):
            context.log(log_type, content, nid)
        else:
            print(f"[{log_type}] (Node: {nid}) {content}")

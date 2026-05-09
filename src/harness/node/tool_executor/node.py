import json
import uuid
import datetime
from typing import Dict, Any
from json_repair import repair_json
from src.harness.node.base import BaseNode
from src.harness.tools.base_tool import BaseToolDispatcher


class Node(BaseNode):
    """工具执行节点：独立完成参数解析与工具分发"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        response = inputs.get("response")
        
        tool_calls = self._extract_tool_calling(response)
        tool_messages = []

        for tc in tool_calls:
            original_tool_name = tc.function.name
            arguments_str = tc.function.arguments
            arguments = {}

            if arguments_str:
                try:
                    arguments = json.loads(arguments_str)
                except json.JSONDecodeError:
                    try:
                        arguments = repair_json(arguments_str, return_objects=True)
                    except Exception:
                        pass

            if not isinstance(arguments, dict):
                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": original_tool_name,
                    "content": "❌ 系统拦截：工具参数格式严重损坏，请检查 JSON 格式！"
                })
                continue

            args_str = ", ".join([f"{k}={repr(v)}" for k, v in arguments.items()])
            self.log(context, "TOOL_CALL", f"🔧 助手调起工具: {original_tool_name}({args_str})", {"arguments": arguments})

            # 核心改动：使用 BaseToolDispatcher 统一调度
            try:
                result_str = BaseToolDispatcher.dispatch(original_tool_name, arguments, context=context)
            except Exception as e:
                result_str = json.dumps({"error": str(e)}, ensure_ascii=False)

            self.log(context, "TOOL", f"📦 工具回传结果: {result_str}")

            finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                parsed_res = json.loads(result_str)
                if isinstance(parsed_res, dict):
                    parsed_res["timestamp"] = finish_time
                    final_content = json.dumps(parsed_res, ensure_ascii=False)
                else:
                    final_content = json.dumps({"content": parsed_res, "timestamp": finish_time}, ensure_ascii=False)
            except json.JSONDecodeError:
                final_content = json.dumps({"content": result_str, "timestamp": finish_time}, ensure_ascii=False)

            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": original_tool_name,
                "content": final_content
            })

        return {"default": tool_messages}

    def _extract_tool_calling(self, response) -> list:
        if hasattr(response, 'choices') and len(response.choices) > 0:
            return getattr(response.choices[0].message, "tool_calls", []) or []
        return []
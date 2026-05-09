import json
import os
from typing import Dict, Any
from harness.node.base import BaseNode
from harness.tools.base_tool import BaseToolDispatcher
from json_repair import repair_json


class Node(BaseNode):
    """文件输出循环节点：封装思考->调用工具->验收的完整循环逻辑"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        tools = inputs.get("tools", context.global_tool_kit())
        file_path = self.config.get("file_path", f"{context.workplace}/FINISHED.md")

        step = 0
        max_steps = 500

        while step < max_steps:
            step += 1
            try:
                response = context.model.chat(messages=messages, tools=tools)
                
                assistant_msg = response.choices[0].message
                messages.append(assistant_msg.model_dump(exclude_none=True))
                
                tool_calls = self._extract_tool_calling(response)

                if not tool_calls:
                    messages.append({"role": "user", "content": "检测到你没有调用任何工具，如已完成任务，请调用 task_done 总结该阶段任务"})
                    continue

                tool_messages = await self._run_tool_calling(response, context)
                if tool_messages:
                    messages.extend(tool_messages)

                if self._check_completed(tool_calls):
                    if self._check_file_exist(file_path):
                        return {"default": messages}
                    else:
                        messages.append({"role": "user", "content": f"检测到你调用了 task_done，但目标文件 {file_path} 尚未生成。请检查是否生成在了其他路径，并及时生成目标文件。"})
                        continue

            except Exception as e:
                self.log(context, "ERROR", f"❌ 运行发生异常: {e}")
                context._cleanup_resources()
                context.save_checkpoints()
                break

        if step >= max_steps and context.state != "COMPLETED":
            context.state = "ERROR"
            context._cleanup_resources()
            context.save_checkpoints()
            self.log(context, "ERROR", f"❌ 任务失败: 超出最大思考步数 ({max_steps})")

        return {"default": messages}

    def _extract_tool_calling(self, response) -> list:
        if hasattr(response, 'choices') and len(response.choices) > 0:
            return getattr(response.choices[0].message, "tool_calls", []) or []
        return []

    def _check_completed(self, tool_calling: list) -> bool:
        return any(tc.function.name == "task_done" for tc in tool_calling)

    def _check_file_exist(self, file_path: str) -> bool:
        return os.path.exists(file_path)

    async def _run_tool_calling(self, response, context) -> list:
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

            from datetime import datetime
            finish_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

        return tool_messages
import asyncio
import importlib
import inspect
import json
from typing import Dict, Optional
import uuid
from src.models.model import Model
from src.plugins.plugin_manager import get_plugin_tool_info, get_plugin_config, init_config_data

TASK_POOL = []
TASK_INSTANCES = {}
def set_task_state(task_id, state):
    for t in TASK_POOL:
        if t["id"] == task_id:
            t["state"] = state
            break

def delete_task(task_id):
    global TASK_POOL
    TASK_POOL = [t for t in TASK_POOL if t["id"] != task_id]
    if task_id in TASK_INSTANCES:
        del TASK_INSTANCES[task_id]

def kill_task(task_id):
    """全局方法：强制关闭 Task 线程"""
    if task_id in TASK_INSTANCES:
        TASK_INSTANCES[task_id].kill()
        set_task_state(task_id, "killed")
        return True
    return False

class Task:
    VALID_STATES = ["waiting", "handling", "completed"]
    def __init__(self, task_detail: Dict, judge_mode: bool, system_prompt: str, task_histories: str = None, task_id: str = None):
        self.run_result = None
        for key in ["title", "desc", "deliverable", "worker", "judger", "available_tools"]:
            if key not in task_detail.keys():
                raise ValueError(f"Missing key '{key}' in task details")
        self.judge_mode = judge_mode
        self.task_detail = task_detail
        self.client = Model(task_detail['worker']).client
        if judge_mode:
            self.eval_client = Model(task_detail['judger']).client
        self.max_len = 20
        self.current_history = []
        self.eval_history = []
        self.system_prompt = system_prompt
        self.task_histories = task_histories
        self.task_id = task_id or str(uuid.uuid4())
        self._killed = False
        TASK_POOL.append({"name": task_detail.get('title', 'Unknown'), "id": self.task_id, "state": "running"})
        TASK_INSTANCES[self.task_id] = self
    def _clean_json_string(self, text: str) -> str:
        """辅助方法：清理模型输出的 Markdown 标记，提取纯 JSON 字符串"""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def kill(self):
        self._killed = True
        print(f"⚠️ [Task] 收到Kill指令，准备直接关闭任务 {self.task_id} 线程...")

    def _check_kill(self):
        """无需保留节点状态，直接抛异常中止"""
        if self._killed:
            raise InterruptedError(f"任务 {self.task_id} 被手动强制关闭。")

    def run(self, suggestion: str = None, max_steps: int = 50):
        init_config_data()

        if not suggestion:
            sys_prompt = (
                "你是一个高级智能助手（Worker），负责执行子任务并善用工具。\n"
                "【严格输出规范：必须返回纯JSON对象，不要输出任何额外的说明文字】\n"
                "1. 当你需要思考或计划调用工具时，返回：{\"status\": \"working\", \"thought\": \"你的思考过程\"}\n"
                "2. 当你最终完成任务或确认无法完成时，返回：{\"status\": \"completed\", \"task_result\": true或false, \"summary\": \"最终交付物或失败原因\"}\n"
                "【重要交付规范】\n"
                "1. 质检员（QA）只能看到你 completed 状态下的 summary，看不到你之前的 thought。\n"
                "2. 如果没有直接产生文件，必须把交付的完整文本写在 summary 里；如果有生成文件，写明文件绝对路径和内容简要说明。"
            )
            self.current_history.append({"role": "system", "content": sys_prompt})
            prompt = f"{self.system_prompt}\n\n请你完成当前阶段的子任务。\n记住，你的回复必须是合法的纯JSON格式，不需要任何Markdown标记！"
            if self.task_histories:
                prompt += f"\n\n[前置任务情况]\n{self.task_histories}"
            self.current_history.append({"role": "user", "content": prompt})
        else:
            self.current_history.append(
                {"role": "user", "content": f"QA反馈不通过：{suggestion}\n请修正后重新提交(保持纯JSON格式)。"})

        available_tools = self.task_detail.get('available_tools', [])
        if isinstance(available_tools, str):
            available_tools = [available_tools] if available_tools else []
        tools_info = get_plugin_tool_info(available_tools)

        model_name = self.task_detail["worker"].split(":")[-1] if ':' in self.task_detail["worker"] else \
            self.task_detail["worker"]

        step = 0
        while step < max_steps:
            self.memory_flush()
            self._check_kill()
            step += 1
            try:
                kwargs = {
                    "model": model_name,
                    "messages": self.current_history,
                }
                if tools_info:
                    kwargs["tools"] = tools_info

                response = self.client.chat.completions.create(**kwargs)
                message = response.choices[0].message

                # 记录模型的原始回复
                assist_msg = {"role": "assistant", "content": message.content}
                if message.tool_calls:
                    assist_msg["tool_calls"] = [
                        {
                            "id": t.id, "type": t.type,
                            "function": {"name": t.function.name, "arguments": t.function.arguments}
                        } for t in message.tool_calls
                    ]
                self.current_history.append(assist_msg)

                content_dict = {}
                if message.content and message.content.strip():
                    raw_content = message.content.strip()
                    print(f"| 🤖 Worker: {raw_content}")

                    cleaned_content = self._clean_json_string(raw_content)
                    try:
                        content_dict = json.loads(cleaned_content)
                    except json.JSONDecodeError as e:
                        self.current_history.append({"role": "user",
                                                     "content": f"输出非合法JSON，请修正。请只输出纯JSON，不要包含多余文字。错误: {e}"})
                        continue

                if content_dict.get("status") == "completed" and not message.tool_calls:
                    self.run_result = content_dict
                    return content_dict

                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        arguments_str = tool_call.function.arguments
                        print(f"| 🔎 Worker Tool: {tool_name}({arguments_str})")
                        try:
                            mcp_type, func_name = tool_name.split('__', 1)
                            arguments = json.loads(arguments_str) if arguments_str else {}
                            result = self._execute_tool(mcp_type, func_name, arguments)
                        except Exception as e:
                            result = f"Tool Execution Error: {str(e)}"
                        print(f"| 😇 Tool Result: {str(result)[:200]}...")
                        self.current_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": str(result)
                        })
            except Exception as e:
                print(f"API 调用发生意外异常: {e}")
                raise InterruptedError(f"API意外中断: {e}")

        return {"task_result": False, "summary": f"Worker超出最大思考步数({max_steps})，被强制终止。"}

    def _execute_tool(self, mcp_type: str, func_name: str, arguments: dict):
        plugin_config = get_plugin_config(mcp_type)
        if not plugin_config:
            raise ValueError(f"未找到插件配置：{mcp_type}")
        try:
            module_path = f"src.plugins.plugin_collection.{mcp_type}"
            plugin_module = importlib.import_module(module_path)
        except ImportError as e:
            try:
                plugin_module = importlib.import_module(mcp_type)
            except ImportError:
                raise ValueError(f"导入插件包失败 {mcp_type}: {e}")
        if not hasattr(plugin_module, func_name):
            raise ValueError(f"插件包 {mcp_type} 中无函数：{func_name}")

        target_func = getattr(plugin_module, func_name)

        if inspect.iscoroutinefunction(target_func):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                result = asyncio.get_event_loop().run_until_complete(target_func(**arguments))
            else:
                result = asyncio.run(target_func(**arguments))
        else:
            result = target_func(**arguments)

        return result if result else "Success (No Output)"

    def run_eval(self, max_steps: int = 30):
        self.eval_history = []
        sys_prompt = (
            "你是一个严格且专业的项目质检员（QA）。\n"
            "【严格输出规范：必须返回纯JSON对象，不要包含其他说明文字】\n"
            "1. 当你需要分析、思考或调用工具检查交付物时，返回：{\"status\": \"evaluating\", \"thought\": \"你的评估思路\"}\n"
            "2. 质检完成时，返回：{\"status\": \"completed\", \"eval_result\": true或false, \"suggestion\": \"失败原因/修改建议 或 成功的评价\"}\n"
            "【质检核心标准】\n"
            "严格对照当前子任务要求进行逐项检查。发现遗漏、幻觉、格式错误判定为不通过。绝不能代替Worker执行任务！"
        )
        self.eval_history.append({"role": "system", "content": sys_prompt})
        prompt = f"{self.system_prompt}\n\n请完成当前阶段的质检：\nWorker的交付内容：{json.dumps(self.run_result, ensure_ascii=False)}\n【参考】前置任务日志：{self.task_histories}\n请直接输出合法的纯JSON格式回复。"
        self.eval_history.append({"role": "user", "content": prompt})

        available_tools = self.task_detail.get('available_tools', [])
        if isinstance(available_tools, str):
            available_tools = [available_tools] if available_tools else []
        tools_info = get_plugin_tool_info(available_tools)

        model_name = self.task_detail["judger"].split(":")[-1] if ':' in self.task_detail["judger"] else \
            self.task_detail["judger"]

        step = 0
        while step < max_steps:
            self._check_kill()
            step += 1
            try:
                kwargs = {
                    "model": model_name,
                    "messages": self.eval_history,
                }
                if tools_info:
                    kwargs["tools"] = tools_info

                response = self.eval_client.chat.completions.create(**kwargs)
                message = response.choices[0].message

                assist_msg = {"role": "assistant", "content": message.content}
                if message.tool_calls:
                    assist_msg["tool_calls"] = [
                        {
                            "id": t.id, "type": t.type,
                            "function": {"name": t.function.name, "arguments": t.function.arguments}
                        } for t in message.tool_calls
                    ]
                self.eval_history.append(assist_msg)

                content_dict = {}
                if message.content and message.content.strip():
                    raw_content = message.content.strip()
                    print(f"| 🤖 Judger: {raw_content}")

                    cleaned_content = self._clean_json_string(raw_content)
                    try:
                        content_dict = json.loads(cleaned_content)
                    except json.JSONDecodeError as e:
                        self.eval_history.append(
                            {"role": "user", "content": f"输出非合法JSON，请修正。请只输出纯JSON，错误: {e}"})
                        continue

                if content_dict.get("status") == "completed" and not message.tool_calls:
                    return content_dict

                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        arguments_str = tool_call.function.arguments
                        print(f"| 🔎 Judger Tool: {tool_name}({arguments_str})")

                        try:
                            mcp_type, func_name = tool_name.split('__', 1)
                            arguments = json.loads(arguments_str) if arguments_str else {}
                            result = self._execute_tool(mcp_type, func_name, arguments)
                        except Exception as e:
                            result = f"Tool Execution Error: {str(e)}"

                        print(f"| 😇 Tool Result: {str(result)[:200]}...")
                        self.eval_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": str(result)
                        })

            except Exception as e:
                print(f"API 调用发生意外异常: {e}")
                raise InterruptedError(f"API意外中断: {e}")

        return {"eval_result": False, "suggestion": "QA质检过程超出最大思考步数。"}

    def run_pipeline(self):
        try:
            result_history = []
            run_result = self.run()
            result_history.append(str(run_result))
            if run_result.get("task_result") and self.judge_mode:
                eval_result = self.run_eval()
                result_history.append(str(eval_result))
                if not eval_result.get("eval_result"):
                    suggestion = f"该阶段的质检不通过；质检建议：{eval_result.get('suggestion')}"
                    print(f"[QA 打回修改] {suggestion}")
                    run_result = self.run(suggestion=suggestion)
                    result_history.append(str(run_result))
                    eval_result = self.run_eval()
                    result_history.append(str(eval_result))
                    if not eval_result.get("eval_result"):
                        final_failure = {"task_result": False, "desc": "模型尝试两次修改后均未通过QA，子任务宣告失败。"}
                        result_history.append(str(final_failure))
            set_task_state(self.task_id, "completed")
            return result_history
        except InterruptedError as e:
            set_task_state(self.task_id, "killed")
            raise e

        except Exception as e:
            set_task_state(self.task_id, "error")
            raise e

    def memory_flush(self, check_mode=True, max_tokens=100000):
        """
        阶段性记忆压缩：结合轮数与 Token 数量进行双重判断。
        直接在 current_history 上让大模型总结，随后抹除中间部分的旧记忆。
        """
        if not check_mode:
            return
        messages_str = json.dumps(self.current_history, ensure_ascii=False)
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")
            current_tokens = len(encoding.encode(messages_str))
        except ImportError:
            current_tokens = len(messages_str) // 2  # 更保守的估算

        if len(self.current_history) <= self.max_len and current_tokens <= max_tokens:
            return
        print(f"⚠️ [Memory Flush] 触发记忆压缩：当前 {len(self.current_history)} 轮，共计约 {current_tokens} tokens。")
        self.current_history.append({
            "role": "user",
            "content": "【系统紧急通知】已达最大记忆容量或 Token 限制，即将压缩前面的对话记录。请先梳理一下关键重要信息，做一下阶段性总结和存档再继续任务。"
        })
        model_name = self.task_detail["worker"].split(":")[-1] if ':' in self.task_detail["worker"] else \
        self.task_detail["worker"]
        kwargs = {
            "model": model_name,
            "messages": self.current_history,
        }
        response = self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        assist_msg = {"role": "assistant", "content": message.content}
        self.current_history.append(assist_msg)
        print(f"🧠 Task归档完成，生成备忘录长度: {len(message.content)} 字符")
        start_idx = 2  # 必须保留前2条（System Prompt 和 初始 User Prompt）
        keep_recent = 18  # 期望保留的尾部记录数（注意：这里包含了刚刚生成的1条通知 + 1条总结）

        split_idx = len(self.current_history) - keep_recent

        if split_idx > start_idx:
            # 往前寻找安全边界，避开切断 tool_call 链条
            while split_idx > start_idx:
                curr_msg = self.current_history[split_idx]
                prev_msg = self.current_history[split_idx - 1]
                if curr_msg.get("role") == "tool":
                    split_idx -= 1
                    continue
                if prev_msg.get("role") == "assistant" and prev_msg.get("tool_calls"):
                    split_idx -= 1
                    continue
                break
        if split_idx < start_idx:
            split_idx = start_idx
        self.current_history = self.current_history[0:start_idx] + self.current_history[split_idx:]

        print("✅ [Memory Flush] 记忆清理完毕！已安全避开 Tool Call 链条完成流水线截断。")

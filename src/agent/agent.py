import datetime
import os
import time
import json
import threading
import uuid
from queue import PriorityQueue, Empty

from src.loader.memory import Memory
from src.models.model import Model
from src.plugins.plugin_manager import parse_tool

from src.plugins.route.agent_tool import AGENT_TOOLS
from src.plugins.route.base_tool import BASE_TOOLS
from src.utils.config import (
    get_agent_model, SOUL_MD_PATH, CHECKPOINT_PATH, TOOL_INDEX_FILE
)

from json_repair import repair_json

MESSAGE_QUEUE = PriorityQueue()

PRIORITY_MAP = {
    "owner_message": 100,
    "project_message": 80,
    "schedule": 60,
    "rss_update": 40,
    "heartbeat": 20
}

ROOT = False


def add_message(message: dict):
    msg_type = message.get("type", "heartbeat")
    priority = PRIORITY_MAP.get(msg_type, 10)
    MESSAGE_QUEUE.put((-priority, time.time(), message))


class Agent:
    def __init__(self, name=None, checkpoint_path=None, warm_up=None):
        if not name:
            name = get_agent_model()
        self.name = name
        self.state = "idle"
        self.model = Model(self.name)
        self.agent_session_id = f"agent_main_{uuid.uuid4().hex[:8]}"
        self.model.bind_task(self.agent_session_id, "AgentMain")
        with open(SOUL_MD_PATH, "r", encoding="utf-8") as f:
            soul_md = f.read()

        self.system_prompt = soul_md
        self.current_history = [{"role": "system", "content": self.system_prompt}]
        self.max_len = 150
        self.memory = Memory()
        self.checkpoint_path = checkpoint_path or CHECKPOINT_PATH
        self.pending_force_push = []
        self._lock = threading.Lock()
        self.window_token = 0
        self._stop_event = threading.Event()
        self.dynamic_tools = []
        if warm_up:
            with open(warm_up, "r", encoding="utf-8") as f:
                warm_up_content = json.loads(f.read())
                self.current_history.extend(warm_up_content)

    def stop(self):
        self._stop_event.set()

    def _append_history(self, message: dict):
        self.current_history.append(message)
        try:
            self.memory.add(message)
            self.save_checkpoint()
        except Exception as e:
            print(f"⚠️ [Memory] 落盘失败: {e}")

    def force_push(self, content, source=None):
        if source:
            formatted_content = f"【收到来自 {source} 的指令】{content}"
        else:
            formatted_content = content
        if self.state == "idle":
            add_message({
                "type": "owner_message",
                "content": formatted_content
            })
        else:
            with self._lock:
                self.pending_force_push.append(formatted_content)

    def _track_token_usage(self, response):
        """精准统计 API Token，防止重复累加"""
        if hasattr(response, "usage") and response.usage is not None:
            self.window_token = response.usage.total_tokens

    def _checker(self, step: int):
        local_push = []
        with self._lock:
            if self.pending_force_push:
                local_push = self.pending_force_push.copy()
                self.pending_force_push.clear()

        if local_push:
            for cnt, item in enumerate(local_push, 1):
                local_push[cnt - 1] = f"{cnt} | " + item
            content = "\n".join(local_push)
            self._append_history({
                "role": "user",
                "content": f"[System Warning] You should suspend your action and handle this message first!\n{content}"
            })
        self._check_and_summarize_memory()

    def process_message(self, message: dict):
        self.state = "handling"
        msg_type = message.get("type")
        msg_content = message.get("content")
        print(f"\n🔔 [Agent 抓取消息] 类型: {msg_type} | 内容: {msg_content}")
        self._append_history({"role": "user", "content": f"🔔 收到系统消息 (类型: {msg_type}):\n{msg_content}"})

        max_steps = 1000

        for step in range(max_steps):
            try:
                current_tools = list(BASE_TOOLS) + list(AGENT_TOOLS)
                if self.dynamic_tools:
                    current_tools.extend([item["schema"] for item in self.dynamic_tools])

                response = self.model.chat(messages=self.current_history, tools=current_tools)
                self._track_token_usage(response)

                msg_resp = response.choices[0].message
                assist_msg = {"role": "assistant", "content": msg_resp.content or ""}

                if msg_resp.tool_calls:
                    assist_msg["tool_calls"] = [
                        {
                            "id": t.id,
                            "type": t.type,
                            "function": {"name": t.function.name, "arguments": t.function.arguments}
                        } for t in msg_resp.tool_calls
                    ]

                self._append_history(assist_msg)

                if msg_resp.content:
                    print(f"🤖 助手思考: {msg_resp.content}")
                if not msg_resp.tool_calls:
                    print("✅ 消息处理闭环结束。")
                    self.state = "idle"
                    break

                for tool_call in msg_resp.tool_calls:
                    tool_name = tool_call.function.name
                    arguments_str = tool_call.function.arguments
                    arguments = {}
                    if arguments_str:
                        try:
                            arguments = json.loads(arguments_str)
                        except json.JSONDecodeError as e:
                            print(f"⚠️ 标准 JSON 解析失败，尝试容错修复: {e}")
                            if repair_json:
                                try:
                                    arguments = repair_json(arguments_str, return_objects=True)
                                    print("✅ json-repair 修复成功！")
                                except Exception as repair_e:
                                    print(f"❌ json-repair 修复失败: {repair_e}")
                    if not isinstance(arguments, dict):
                        error_msg = "❌ 系统拦截：工具参数格式严重损坏。可能是由于命令过长导致的截断或转义错误，建议分批运行指令！！！"
                        print(error_msg)
                        self._append_history({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": error_msg
                        })
                        continue

                    if tool_name in ["execute_command", "close_shell"]:
                        arguments["session_id"] = self.agent_session_id

                    if isinstance(arguments, dict):
                        args_str = ", ".join([f'{k}={repr(v)}' for k, v in arguments.items()])
                    else:
                        args_str = str(arguments)
                    print(f"🔧 助手调起工具: {tool_name}({args_str})")
                    target_route = None
                    target_plugin = None

                    from src.plugins.route.agent_tool import AGENT_TOOL_FUNCTIONS
                    agent_tool_names = list(AGENT_TOOL_FUNCTIONS.keys())

                    if tool_name in agent_tool_names:
                        target_route = "agent"
                        target_plugin = "agent_tool"
                    else:
                        for tool_item in self.dynamic_tools:
                            if tool_item.get("funct") == tool_name:
                                target_route = tool_item.get("route")
                                target_plugin = tool_item.get("plugin")
                                break

                        if not target_route or not target_plugin:
                            if os.path.exists(TOOL_INDEX_FILE):
                                with open(TOOL_INDEX_FILE, "r", encoding="utf-8") as f:
                                    for line in f:
                                        if not line.strip():
                                            continue
                                        tool_info = json.loads(line)
                                        if tool_info["func"] == tool_name:
                                            target_route = tool_info["route"]
                                            target_plugin = tool_info["plugin"]
                                            break

                    result_str, new_schema_info = parse_tool(tool_name, arguments, route=target_route, plugin=target_plugin)
                    finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    if new_schema_info:
                        schemas_to_add = new_schema_info if isinstance(new_schema_info, list) else [new_schema_info]
                        for schema_item in schemas_to_add:
                            new_funct_name = schema_item["funct"]
                            found_idx = -1
                            for i, existing_item in enumerate(self.dynamic_tools):
                                if existing_item.get("funct") == new_funct_name:
                                    found_idx = i
                                    break
                            if found_idx != -1:
                                self.dynamic_tools[found_idx] = schema_item
                            else:
                                self.dynamic_tools.append(schema_item)

                    if result_str == "__AGENT_PAUSE__":
                        print("⏸️ Agent 已将当前任务放入挂起表，准备处理下一条消息...")
                        time_aware_content = f"[finish at {finish_time}]\n工具调用成功，正在挂起任务，请耐心等待处理"
                        self._append_history({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": time_aware_content
                        })
                        self.state = "idle"
                        return

                    print(f"📦 工具回传结果: {result_str}")
                    time_aware_content = f"[finish at {finish_time}]\n{result_str}"
                    self.current_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": time_aware_content
                    })

                self._checker(step)

            except KeyboardInterrupt:
                self.state = "idle"
                print("⚠️ [Agent] 检测到强制中断 (Ctrl+C)，保存现场...")
                if self.current_history and self.current_history[-1].get("role") == "assistant" and self.current_history[-1].get("tool_calls"):
                    self.current_history.pop()
                    print("⚠️ 已自动撤销未完成的 tool_calls 记录")
                self.current_history.append({
                    "role": "assistant",
                    "content": "⚠️ [系统提示] Agent 运行被用户或系统强制中断 (Ctrl+C)。"
                })
                self.save_checkpoint()
                raise
            except Exception as e:
                self.state = "idle"
                print(f"❌ [Agent] 大模型交互断层: {e}")
                if self.current_history and self.current_history[-1].get("role") == "assistant" and self.current_history[-1].get("tool_calls"):
                    self.current_history.pop()
                    print("⚠️ 已自动撤销引发异常的 tool_calls 记录")
                self.current_history.append({
                    "role": "assistant",
                    "content": f"❌ [系统报错] Agent 遭遇意外交互断层，当前处理已终止。错误信息：{e}"
                })
                self.save_checkpoint()
                break
        try:
            self._check_and_summarize_memory()
        except Exception as e:
            print(f"压缩记忆失败：{e}")

    def _check_and_summarize_memory(self, check_mode=True):
        max_tokens = 100000
        if check_mode and len(self.current_history) < 150 and self.window_token < max_tokens:
            return
        print(f"🗜️ 记忆容量到达 {len(self.current_history)} 条 (约 {self.window_token} tokens)，触发自我归档...")
        alert_prompt = """【系统严重警告：大脑记忆容量即将溢出！！！】
为了防止记忆断层，系统即将物理抹除你最早期的一批记忆。
请你现在亲自对**此前的关键对话、事件**进行全面总结，提取出核心事件、任务进度、你的关键决策、当前需要加载的skill等，形成一份“早期记忆备忘录”。
直接用自然语言输出。这份备忘录将作为你未来回忆那段时光的唯一凭证，也是你承上启下的节点，请务必保证包含影响任务推进的关键信息！但也要尽量保持简洁和少废话，防止备忘录越来越长！总结完本次对话后，如果已加载的skill记录消失，则需要在下轮对话重新加载遗失的skill"""
        self._append_history({"role": "user", "content": alert_prompt})
        try:
            response = self.model.chat(messages=self.current_history)
            self._track_token_usage(response)

            archive_content = response.choices[0].message.content.strip()
            print(f"🧠 Agent归档完成，生成备忘录长度: {len(archive_content)} 字符")
            self._append_history({"role": "assistant", "content": f"【早期记忆备忘录】\n{archive_content}"})

            start_idx = 1
            keep_recent = 20
            split_idx = len(self.current_history) - keep_recent
            if split_idx > start_idx:
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
            self.current_history = [self.current_history[0]] + self.current_history[split_idx:]
            self.dynamic_tools.clear()
            print("✅ Agent记忆清理完毕！已安全避开 Tool Call 链条完成流水线截断。")
            self.window_token = 0
            self.save_checkpoint()
        except Exception as e:
            print(f"❌ 记忆存档发生异常: {e}")

    def sensor(self):
        print("🟢 Agent 主核运转，正在监听优先队列...")
        while not self._stop_event.is_set():
            try:
                priority, timestamp, msg = MESSAGE_QUEUE.get(timeout=1)
                self.process_message(msg)
                MESSAGE_QUEUE.task_done()
            except Empty:
                continue
            except Exception as e:
                print(f"❌ 队列处理异常: {e}")

    def save_checkpoint(self, filepath="src\\agent\\checkpoint.json"):
        save_path = filepath or self.checkpoint_path
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(self.current_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ [Checkpoint] 保存检查点失败: {e}")

    @classmethod
    def load_checkpoint(cls, filepath="src/agent/checkpoint.json", name="openai:deepseek-chat"):
        agent = cls(name=name, checkpoint_path=filepath)
        try:
            if not os.path.exists(filepath):
                print(f"⚠️ [Checkpoint] 找不到文件: {filepath}，将以全新状态启动并创建该文件。")
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                agent.save_checkpoint(filepath)
                return agent
            with open(filepath, "r", encoding="utf-8") as f:
                history = json.load(f)
            if isinstance(history, list) and len(history) > 0:
                last_msg = history[-1]
                if last_msg.get("role") == "assistant" and last_msg.get("tool_calls"):
                    print("🛠️ [Checkpoint] 检测到断点处缺失工具回传结果，自动撤销最近一次未完成的思考...")
                    history.pop()
                agent.current_history = history
                print(f"✅ 成功从 {filepath} 恢复对话历史，共加载了 {len(history)} 条记录。")
            else:
                print(f"⚠️ [Checkpoint] 文件内容为空或格式错误，重置为全新状态。")
                agent.save_checkpoint(filepath)
            return agent
        except Exception as e:
            print(f"❌ [Checkpoint] 恢复检查点失败: {e}，将以全新状态启动。")
            return agent
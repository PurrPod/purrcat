import os
import time
import json
import importlib
from queue import PriorityQueue, Empty
from src.loader.memory import Memory
from src.models.model import Model
from src.plugins.plugin_manager import get_plugin_tool_info, get_plugin_config, init_config_data, register_plugin

MESSAGE_QUEUE = PriorityQueue()
PENDING_TASKS = {}

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

GLOBAL_AGENT_TOOLS = ["manager", "feishu"]

class Agent:
    def __init__(self, name="[1]openai:deepseek-chat", max_len=150, checkpoint_path="src\\agent\\checkpoint.json", warm_up=None):
        init_config_data()
        self.name = name
        self.state = "idle"
        self.client = Model(self.name).client
        with open("src/agent/SOUL.md", "r") as f:
            soul_md = f.read()
        self.system_prompt = (
            soul_md
        )
        self.current_history = [{"role": "system", "content": self.system_prompt}]
        self.max_len = max_len
        self.memory = Memory()
        self.checkpoint_path = checkpoint_path
        if warm_up:
            with open(warm_up, "r") as f:
                warm_up_content = json.loads(f.read())
                self.current_history.extend(warm_up_content)
    def _append_history(self, message: dict):
        """统一管理对话历史：加入内存列表的同时，直接落盘到 Memory 文件"""
        self.current_history.append(message)
        try:
            self.memory.add(message)
            self.save_checkpoint()
        except Exception as e:
            print(f"⚠️ [Memory] 落盘失败: {e}")

    def _execute_tool(self, mcp_type: str, func_name: str, arguments: dict):
        plugin_config = get_plugin_config(mcp_type)
        if not plugin_config:
            try:
                register_plugin(mcp_type)
            except Exception as e:
                return f"❌ [Error]{mcp_type}:{e}"
        try:
            try:
                module_path = f"src.plugins.plugin_collection.{mcp_type}.{mcp_type}"
                plugin_module = importlib.import_module(module_path)
            except ImportError:
                module_path = f"src.plugins.plugin_collection.{mcp_type}"
                plugin_module = importlib.import_module(module_path)
        except ImportError as e:
            return f"❌ 导入插件包失败 {mcp_type}:{e}"
        if not hasattr(plugin_module, func_name):
            return f"❌ 插件包中无函数：{func_name}"
        target_func = getattr(plugin_module, func_name)
        result = target_func(**arguments)
        return result if result is not None else "Success (No Output)"

    def force_push(self, content):
        self._append_history({"role": "user", "content": "[System Warning] You should suspend your action and handle this message first!\n"+content})

    def process_message(self, message: dict):
        self.state = "handling"
        msg_type = message.get("type")
        msg_content = message.get("content")
        chat_id = message.get("chat_id", "owner")
        print(f"\n🔔 [Agent 抓取消息] 类型: {msg_type} | 内容: {msg_content}")
        self._append_history(
            {"role": "user", "content": f"🔔 收到系统消息 (类型: {msg_type}):\n{msg_content}"})

        init_config_data()

        model_name = self.name.split(":")[-1] if ":" in self.name else self.name
        max_steps = 1000

        for step in range(max_steps):
            try:
                tools_info = get_plugin_tool_info(GLOBAL_AGENT_TOOLS)
                kwargs = {"model": model_name, "messages": self.current_history}
                
                self._check_and_summarize_memory()
                if tools_info:
                    kwargs["tools"] = tools_info
                response = self.client.chat.completions.create(**kwargs)
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
                    break

                for tool_call in msg_resp.tool_calls:
                    tool_name = tool_call.function.name
                    arguments_str = tool_call.function.arguments
                    print(f"🔧 助手调起工具: {tool_name}({arguments_str})")
                    try:
                        delimiter = '__' if '__' in tool_name else '/'
                        mcp_type, func_name = tool_name.split(delimiter, 1) if delimiter in tool_name else (tool_name,tool_name)
                        arguments = json.loads(arguments_str) if arguments_str else {}
                        result = self._execute_tool(mcp_type, func_name, arguments)

                        if result == "__AGENT_PAUSE__":
                            print("⏸️ Agent 已将当前任务放入挂起表，准备处理下一条消息...")
                            self._append_history({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_name,
                                "content": "工具调用成功，正在挂起任务，请耐心等待处理"
                            })
                            self.state = "idle"
                            return
                    except Exception as e:
                        result = f"Error: {str(e)}"
                    print(f"📦 工具回传结果: {str(result)}...")

                    self._append_history({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": str(result)
                    })

            except Exception as e:
                print(f"❌ 大模型交互断层: {e}")
                break

        self.state = "idle"
        try:
            self._check_and_summarize_memory()
        except Exception as e:
            print(f"压缩记忆失败：{e}")

    def _check_and_summarize_memory(self, check_mode=True):
        messages_str = json.dumps(self.current_history, ensure_ascii=False)
        max_tokens = 100000
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")
            current_tokens = len(encoding.encode(messages_str))
        except ImportError:
            current_tokens = len(messages_str) // 2

        if check_mode:
            if len(self.current_history) < self.max_len and current_tokens < max_tokens:
                return

        print(f"🗜️ 记忆容量到达 {len(self.current_history)} 条 (约 {current_tokens} tokens)，触发自我归档...")

        alert_prompt = """【系统严重警告：大脑记忆容量即将溢出！！！】
为了防止记忆断层，系统即将物理抹除你最早期的一批记忆。
请你现在亲自对**此前的所有对话、事件和执行记录**进行全面总结，提取出核心事件、任务进度、你的关键决策以及对用户的认知，形成一份“早期记忆备忘录”。
直接用自然语言输出。这份备忘录将作为你未来回忆那段时光的唯一凭证，也是你承上启下的节点，请务必保证包含影响任务推进的关键信息！"""

        # 使用 _append_history，保证这句警告也能记录到本地日志中
        self._append_history({"role": "user", "content": alert_prompt})

        try:
            model_name = self.name.split(":")[-1] if ":" in self.name else self.name
            kwargs = {
                "model": model_name,
                "messages": self.current_history
            }

            # 2. 让大模型基于当前完整的上下文自己做个总结
            response = self.client.chat.completions.create(**kwargs)
            archive_content = response.choices[0].message.content.strip()
            print(f"🧠 Agent归档完成，生成备忘录长度: {len(archive_content)} 字符")

            # 同样使用 _append_history 落盘
            self._append_history({"role": "assistant", "content": f"【早期记忆备忘录】\n{archive_content}"})

            # 3. 物理抹除旧记忆：寻找安全切分点
            start_idx = 1  # Agent 必须保留第 1 条（System Prompt: SOUL.md）
            keep_recent = 20  # Agent 需要的上下文更长，保留最近 20 条（包含刚才的通知和总结）

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
            self.current_history = [self.current_history[0]] + self.current_history[split_idx:]

            print("✅ Agent记忆清理完毕！已安全避开 Tool Call 链条完成流水线截断。")
            self.save_checkpoint()  # 保存截断后的新状态

        except Exception as e:
            print(f"❌ 记忆存档发生异常: {e}")

    def sensor(self):
        print("🟢 Agent 主核运转，正在监听优先队列...")
        while True:
            try:
                priority, timestamp, msg = MESSAGE_QUEUE.get(timeout=1)
                self.process_message(msg)
                MESSAGE_QUEUE.task_done()
            except Empty:
                continue
            except Exception as e:
                print(f"❌ 队列处理异常: {e}")

    def save_checkpoint(self, filepath="src\\agent\\checkpoint.json"):
        """将当前的 current_history 落盘保存到文件"""
        save_path = filepath or self.checkpoint_path
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                # 使用 indent=2 保证生成的 JSON 文件具备可读性
                json.dump(self.current_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ [Checkpoint] 保存检查点失败: {e}")
    @classmethod
    def load_checkpoint(cls, filepath="src/agent/checkpoint.json", name="[1]openai:deepseek-chat",
                        max_len=150):
        agent = cls(name=name, max_len=max_len, checkpoint_path=filepath)

        try:
            if not os.path.exists(filepath):
                print(f"⚠️ [Checkpoint] 找不到文件: {filepath}，将以全新状态启动并创建该文件。")
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                agent.save_checkpoint(filepath)
                return agent
            with open(filepath, "r", encoding="utf-8") as f:
                history = json.load(f)
            if isinstance(history, list) and len(history) > 0:
                agent.current_history = history
                print(f"✅ 成功从 {filepath} 恢复对话历史，共加载了 {len(history)} 条记录。")
            else:
                print(f"⚠️ [Checkpoint] 文件内容为空或格式错误，重置为全新状态。")
                agent.save_checkpoint(filepath)

            return agent

        except Exception as e:
            print(f"❌ [Checkpoint] 恢复检查点失败: {e}，将以全新状态启动。")
            return agent
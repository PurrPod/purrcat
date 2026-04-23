import os
import json
import yaml
from textual import work, on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Static, Input, Markdown

# ==========================================
# 真正的原生调用：实例化并持有全局 Agent
# ==========================================
try:
    from src.agent.agent import Agent

    # 直接拉起你的核心大模型实例，自动加载断点记忆！
    chat_agent = Agent.load_checkpoint()
except Exception as e:
    chat_agent = None
    init_error = str(e)

ASCII_CAT = """\
   /\\_/\\    Catnip AI CLI (Native Core Edition)
  ( o.o )   Type /help for commands. Press Ctrl+C to exit.
   > ^ <    
"""


class ChatMessage(Vertical):
    def __init__(self, role: str, text: str):
        super().__init__()
        self.role = role
        self.text = text

    def compose(self) -> ComposeResult:
        if self.role == "user":
            yield Static("❯ User", classes="role-user")
        elif self.role == "system":
            yield Static("❯ System", classes="role-user")
        else:
            yield Static("❯ CatInCup", classes="role-ai")
        yield Markdown(self.text)


class ChatView(Vertical):
    def compose(self) -> ComposeResult:
        with VerticalScroll(id="chat-history"):
            yield Static(ASCII_CAT, id="welcome-pet")
        with Horizontal(id="input-area"):
            yield Static("❯", id="prompt-char")
            yield Input(placeholder="Ask Catnip natively...", id="chat-input")

    @on(Input.Submitted, "#chat-input")
    def handle_input(self, event: Input.Submitted):
        msg = event.value.strip()
        if not msg: return
        event.input.value = ""

        history = self.query_one("#chat-history")

        if msg.startswith("/"):
            self.execute_slash_command(msg, history)
            return

        # 挂载用户消息
        history.mount(ChatMessage("user", msg))

        # 挂载 Loading 状态
        loading_msg = ChatMessage("ai", "...")
        history.mount(loading_msg)
        history.scroll_end(animate=False)

        # 触发后台线程运算
        self.process_native_agent(msg, loading_msg)

    @work(thread=True, exclusive=True)
    def process_native_agent(self, msg: str, loading_widget: ChatMessage):
        """核心改动：thread=True 将阻塞的模型推流放入独立线程，防止 TUI 卡死"""
        if chat_agent is None:
            self.app.call_from_thread(
                loading_widget.query_one(Markdown).update,
                f"**System Error:** Agent failed to initialize.\n`{init_error}`"
            )
            return

        try:
            # 记录当前记忆长度，方便一会提取增量回复
            start_len = len(chat_agent.current_history)

            # 真实调用！组装你定义的字典格式传入
            chat_agent.process_message({
                "type": "owner_message",
                "content": msg
            })

            # 提取 Agent 在此轮产生的最新文字回复 (过滤掉内部 tool 调用的原始数据)
            new_msgs = chat_agent.current_history[start_len:]
            replies = [
                m.get("content", "") for m in new_msgs
                if m.get("role") == "assistant" and m.get("content")
            ]

            response_text = "\n\n".join(replies) if replies else "*(Agent 运算完毕，已静默挂起或分配工具)*"

            # 因为我们在子线程，所以必须用 call_from_thread 来更新主线程的 UI
            self.app.call_from_thread(loading_widget.query_one(Markdown).update, response_text)
            self.app.call_from_thread(self.query_one("#chat-history").scroll_end, animate=False)

        except Exception as e:
            self.app.call_from_thread(
                loading_widget.query_one(Markdown).update,
                f"**Core Execution Error:**\n```python\n{str(e)}\n```"
            )
            self.app.call_from_thread(self.query_one("#chat-history").scroll_end, animate=False)

    def execute_slash_command(self, cmd: str, history: VerticalScroll):
        history.mount(ChatMessage("user", cmd))
        reply = ""

        try:
            if cmd == "/help":
                reply = (
                    "**Native Commands:**\n"
                    "- `/task` : Read internal tasks\n"
                    "- `/schedule` : Read schedule data\n"
                    "- `/plugin` : Read MCP plugin config\n"
                    "- `/setting` : Read system config\n"
                    "- `/clear` : Clear screen"
                )

            elif cmd == "/clear":
                for child in history.children:
                    if child.id != "welcome-pet": child.remove()
                return

            elif cmd == "/schedule":
                file_path = "data/schedule/schedule.json"
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    reply = "### ⏰ Schedules\n| Title | Time | Description |\n|---|---|---|\n"
                    for t in data.get("tasks", []):
                        reply += f"| {t.get('title', '-')} | {t.get('time', '-')} | {t.get('description', '-')} |\n"
                else:
                    reply = "No schedule found."

            elif cmd == "/plugin":
                file_path = "data/config/configs/mcp_servers.yaml"
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    reply = "### 🔌 MCP Plugins Loaded\n"
                    for name, conf in data.get("mcpServers", {}).items():
                        reply += f"- **{name}**: `{conf.get('command', 'unknown')}`\n"
                else:
                    reply = "No MCP configs found."

            elif cmd == "/setting":
                file_path = "data/config/configs/system.yaml"
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    reply = "### ⚙️ System Settings\n```yaml\n" + yaml.dump(data, allow_unicode=True) + "\n```"
                else:
                    reply = "System settings not found."
            else:
                reply = f"Unknown command: `{cmd}`"

        except Exception as e:
            reply = f"**Command Error:** `{str(e)}`"

        history.mount(ChatMessage("system", reply))
        history.scroll_end(animate=False)
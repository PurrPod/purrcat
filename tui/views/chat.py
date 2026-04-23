import os
import json
import yaml
from datetime import datetime
from textual import work, on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Static, Input, Markdown, ProgressBar, ListView, ListItem

try:
    from src.agent.agent import Agent

    chat_agent = Agent.load_checkpoint()
except Exception as e:
    chat_agent = None
    init_error = str(e)


class ChatMessage(Vertical):
    def __init__(self, role: str, text: str):
        super().__init__()
        self.role = role
        self.text = text
        self.add_class(role)

    def compose(self) -> ComposeResult:
        if self.role == "user":
            yield Static("❯ User", classes="role-user")
        elif self.role == "system":
            yield Static("⚙ System", classes="role-system")
        else:
            yield Static("● CatInCup", classes="role-ai")
        yield Markdown(self.text)


class MainView(Horizontal):
    """全局主视图：Claude Code 极简风格重构版"""

    def compose(self) -> ComposeResult:
        # ======= 左侧区域 (占 4/5) =======
        with Vertical(id="left-pane"):
            # 1. 顶部 1/5：状态与小猫
            with Horizontal(id="top-zone"):
                # ASCII 小猫
                yield Static("  /\\_/\\\n ( o.o )\n  > ^ <", id="cat-ascii")
                # 版本与 Token 进度
                with Vertical(id="status-container"):
                    yield Static("Cat-in-Cup v2.1.114", id="version-text")
                    yield Static("Agent Initialized • Ready for tasks", id="sub-status")
                    yield ProgressBar(total=100, show_eta=False, id="token-progress")

            # 2. 中部 3/5：聊天历史记录
            with VerticalScroll(id="chat-zone"):
                pass  # 动态挂载

            # 3. 底部 1/5：输入区
            with Vertical(id="input-zone"):
                with Horizontal(id="input-row"):
                    yield Static("❯", id="prompt-char")
                    yield Input(placeholder="Bypass permissions on (shift+tab to cycle)...", id="chat-input")
                yield Static("Ctrl+Enter 发送 | Ctrl+K 聚焦 | Ctrl+L 清屏 | Ctrl+P 专注模式", id="shortcut-hint")

        # ======= 右侧区域 (占 1/5) =======
        with VerticalScroll(id="right-pane"):
            yield Static("Spaces", classes="sidebar-title")
            yield ListView(
                ListItem(Static("Main", classes="nav-item"), id="nav-main"),
                ListItem(Static("Task", classes="nav-item"), id="nav-task"),
                id="sidebar-nav"
            )

    def on_mount(self) -> None:
        self.histories = {
            "nav-main": [],
            "nav-task": [ChatMessage("system", "Task history initialized.")]
        }
        self.current_space = "nav-main"
        self.render_history()
        self.query_one("#chat-input", Input).focus()

        # 让小猫眨眼的互动逻辑
        self.blink_state = False
        self.set_interval(3.5, self.blink_cat)

        # 模拟 Token 进度条初始化
        self.query_one("#token-progress", ProgressBar).advance(15)

    def blink_cat(self) -> None:
        """定时切换小猫表情实现眨眼"""
        cat = self.query_one("#cat-ascii", Static)
        if self.blink_state:
            cat.update("  /\\_/\\\n ( o.o )\n  > ^ <")
        else:
            cat.update("  /\\_/\\\n ( -.- )\n  > ^ <")
        self.blink_state = not self.blink_state

    @on(ListView.Selected, "#sidebar-nav")
    def switch_space(self, event: ListView.Selected):
        self.current_space = event.item.id
        self.render_history()

    def render_history(self):
        chat_zone = self.query_one("#chat-zone")
        for child in chat_zone.children:
            child.remove()
        for msg in self.histories.get(self.current_space, []):
            chat_zone.mount(msg)
        chat_zone.scroll_end(animate=False)

    def append_message(self, role: str, text: str):
        msg = ChatMessage(role, text)
        self.histories[self.current_space].append(msg)
        chat_zone = self.query_one("#chat-zone")
        chat_zone.mount(msg)
        chat_zone.scroll_end(animate=False)
        return msg

    @on(Input.Submitted, "#chat-input")
    def handle_force_push(self, event: Input.Submitted):
        msg = event.value.strip()
        if not msg: return
        event.input.value = ""

        if msg.startswith("/"):
            self.execute_slash_command(msg)
            return

        self.append_message("user", msg)
        loading_msg = self.append_message("ai", "...")
        self.process_native_agent(msg, loading_msg)

    @work(thread=True, exclusive=True)
    def process_native_agent(self, msg: str, loading_widget: ChatMessage):
        if chat_agent is None:
            self.app.call_from_thread(
                loading_widget.query_one(Markdown).update,
                f"**System Error:** Agent failed to initialize.\n`{init_error}`"
            )
            return

        try:
            for i in range(3):
                dots = "." * (i + 1)
                self.app.call_from_thread(loading_widget.query_one(Markdown).update, f"{dots}")
                import time;
                time.sleep(0.3)

            start_len = len(chat_agent.current_history)
            chat_agent.process_message({"type": "owner_message", "content": msg})

            # 模拟 Token 进度增长
            self.app.call_from_thread(self.query_one("#token-progress", ProgressBar).advance, 5)

            new_msgs = chat_agent.current_history[start_len:]
            replies = [m.get("content", "") for m in new_msgs if m.get("role") == "assistant" and m.get("content")]
            response_text = "\n\n".join(replies) if replies else "*(Agent 运算完毕)*"

            self.typewriter_effect(loading_widget, response_text)

        except Exception as e:
            self.app.call_from_thread(
                loading_widget.query_one(Markdown).update,
                f"**Core Execution Error:**\n```python\n{str(e)}\n```"
            )
            self.app.call_from_thread(self.query_one("#chat-zone").scroll_end, animate=False)

    def execute_slash_command(self, cmd: str):
        self.append_message("user", cmd)
        reply = f"System executed: {cmd}"
        self.append_message("system", reply)

    def typewriter_effect(self, widget: ChatMessage, text: str):
        markdown = widget.query_one(Markdown)
        current_text = ""
        for char in text:
            current_text += char
            self.app.call_from_thread(markdown.update, current_text)
            self.app.call_from_thread(self.query_one("#chat-zone").scroll_end, animate=False)
            import time;
            time.sleep(0.01)

    def on_key(self, event):
        if event.key == "ctrl+l":
            chat_zone = self.query_one("#chat-zone")
            for child in chat_zone.children:
                child.remove()
            self.histories[self.current_space] = []
        elif event.key == "ctrl+k":
            self.query_one("#chat-input", Input).focus()
        elif event.key == "ctrl+enter":
            input_widget = self.query_one("#chat-input", Input)
            if input_widget.value.strip():
                self.handle_force_push(Input.Submitted(input_widget, input_widget.value))
        elif event.key == "ctrl+p":
            main_layout = self.query_one("#main-layout")
            if "focus-mode" in main_layout.classes:
                main_layout.remove_class("focus-mode")
            else:
                main_layout.add_class("focus-mode")
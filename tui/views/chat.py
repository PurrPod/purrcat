# --- tui/views/chat.py ---

import os
import time
from textual import work, on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Static, Markdown, ProgressBar, ListView, ListItem, TextArea
from textual.events import Event, Key

from tui.api import (
    get_task_list, get_agent_history, get_task_history, force_push_agent, force_push_task,
    get_window_token, get_task_window_token, get_agent_max_token
)


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


class ChatInput(TextArea):
    """支持 Shift+Enter 换行，Enter 发送的多行输入框"""
    BINDINGS = [
        ("enter", "submit", "Submit"),
        ("shift+enter", "newline", "Newline")
    ]

    def action_submit(self):
        text = self.text.strip()
        if text:
            # 触发父视图发送逻辑
            self.app.query_one(MainView).handle_chat_submit(text)
            self.clear()

    def action_newline(self):
        self.insert("\n")

    def on_key(self, event: Key) -> None:
        """底层拦截按键事件，防止被 TextArea 原生的换行覆盖"""
        if event.key == "enter":
            # 阻止默认的换行行为
            event.prevent_default()
            text = self.text.strip()
            if text:
                self.app.query_one(MainView).handle_chat_submit(text)
                self.clear()
        elif event.key in ["shift+enter", "alt+enter"]:
            # 兼容性：某些老旧终端无法区分 shift+enter 和 enter
            # 可以使用 Alt+Enter 兜底来实现换行
            event.prevent_default()
            self.insert("\n")

class MainView(Horizontal):
    """全局主视图：Cat-in-Cup 增强版"""

    def compose(self) -> ComposeResult:
        # ======= 左侧区域 =======
        with Vertical(id="left-pane"):
            with Horizontal(id="top-zone"):
                yield Static("  /\\_/\\\n ( o.o )\n  > ^ <", id="cat-ascii")
                with Vertical(id="status-container"):
                    yield Static("Cat-in-Cup v1.0.0", id="version-text")
                    yield Static("Agent Initialized • Ready for tasks", id="sub-status")
                    yield ProgressBar(total=100, show_eta=False, id="token-progress")

            # 聊天历史区，设置缺口标题
            chat_zone = VerticalScroll(id="chat-zone")
            chat_zone.border_title = "Chat History /"
            yield chat_zone

            # 输入区，设置缺口标题，移除无关说明
            input_zone = Vertical(id="input-zone")
            input_zone.border_title = "Chat Input /"
            with input_zone:
                with Horizontal(id="input-row"):
                    yield Static("❯", id="prompt-char")
                    yield ChatInput(id="chat-input", show_line_numbers=False)

        # ======= 右侧区域 (会话列表) =======
        with VerticalScroll(id="right-pane"):
            yield Static("Spaces", classes="sidebar-title")
            yield ListView(
                ListItem(Static("Main", classes="nav-item"), id="nav-main"),
                id="sidebar-nav"
            )

    def on_mount(self) -> None:
        self.current_space = "nav-main"
        self.last_activity_time = time.time()
        self.blink_state = False

        # 记录已渲染的消息数量，实现增量渲染，防止闪烁
        self.rendered_msg_counts = {"nav-main": 0}

        self.query_one("#chat-input", ChatInput).focus()

        # 挂载定时器：猫咪眨眼与闲置、聊天状态刷新
        self.set_interval(3.0, self.blink_cat)
        self.set_interval(1.0, self.refresh_chat_state)

    async def on_event(self, event: Event) -> None:
        """捕获全局事件，重置闲置计时器"""
        self.last_activity_time = time.time()
        await super().on_event(event)

    def blink_cat(self) -> None:
        """处理猫咪的眨眼与瞌睡状态"""
        cat = self.query_one("#cat-ascii", Static)
        idle_time = time.time() - self.last_activity_time

        # 闲置超过 30 秒则打瞌睡
        if idle_time > 30:
            cat.update("  /\\_/\\\n ( u.u )\n  >   < zZ")
        else:
            if self.blink_state:
                cat.update("  /\\_/\\\n ( o.o )\n  >   <")
            else:
                cat.update("  /\\_/\\\n ( -.- )\n  >   <")
            self.blink_state = not self.blink_state

    @on(ListView.Selected, "#sidebar-nav")
    def switch_space(self, event: ListView.Selected):
        """点击右侧边栏切换会话"""
        self.current_space = event.item.id
        # 切换时清空左侧聊天区，强制下次轮询全部重新渲染
        chat_zone = self.query_one("#chat-zone")
        for child in chat_zone.children:
            child.remove()

        self.rendered_msg_counts[self.current_space] = 0
        self.refresh_chat_state()

    def refresh_chat_state(self):
        """定时拉取最新任务列表和当前会话的对话记录"""
        from tui.api import (
            get_task_list, get_agent_history, get_task_history,
            get_window_token, get_task_window_token,
            get_agent_max_token, get_task_max_token
        )

        # 1. 更新右侧 Task 列表 (仅添加不在列表中的新 Task)
        sidebar = self.query_one("#sidebar-nav", ListView)
        tasks = get_task_list()
        existing_ids = [item.id for item in sidebar.children if item.id]

        for task in tasks:
            task_list_id = f"task-{task['id']}"
            if task_list_id not in existing_ids:
                new_item = ListItem(Static(f"{task['name']}", classes="nav-item"), id=task_list_id)
                sidebar.append(new_item)
                if task_list_id not in self.rendered_msg_counts:
                    self.rendered_msg_counts[task_list_id] = 0

        # 2. 根据选中的会话获取历史记录、当前 window_token 和对应压缩阈值 max_token
        if self.current_space == "nav-main":
            history = get_agent_history()
            current_token = get_window_token()
            max_token = get_agent_max_token()  # 100000
        else:
            task_id = self.current_space.replace("task-", "")
            history = get_task_history(task_id)
            current_token = get_task_window_token(task_id)
            max_token = get_task_max_token()  # 120000

        # 3. 更新 Token 进度条 (window_token / max_token)
        progress = self.query_one("#token-progress", ProgressBar)
        progress.total = max_token
        progress.update(progress=min(current_token, max_token))

        # 4. 增量渲染聊天历史
        chat_zone = self.query_one("#chat-zone")
        rendered_count = self.rendered_msg_counts.get(self.current_space, 0)

        if len(history) > rendered_count:
            for msg in history[rendered_count:]:
                role = msg.get("role", "system")
                content = msg.get("content", "")
                if content:
                    chat_zone.mount(ChatMessage(role, content))

            self.rendered_msg_counts[self.current_space] = len(history)
            chat_zone.scroll_end(animate=False)

    def handle_chat_submit(self, text: str):
        """处理输入内容的发送"""
        if self.current_space == "nav-main":
            force_push_agent(text)
        else:
            task_id = self.current_space.replace("task-", "")
            force_push_task(task_id, text)

        # 预加载用户消息到 UI 防止视觉延迟，稍后的轮询会自动校准
        chat_zone = self.query_one("#chat-zone")
        chat_zone.mount(ChatMessage("user", text))
        self.rendered_msg_counts[self.current_space] += 1
        chat_zone.scroll_end(animate=False)
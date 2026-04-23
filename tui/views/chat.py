import os
import time
import json
from textual import work, on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Static, Markdown, ProgressBar, ListView, ListItem, TextArea
from textual.events import Event, Key

from tui.api import (
    get_task_list, get_agent_history, get_task_history, force_push_agent, force_push_task,
    get_window_token, get_task_window_token, get_agent_max_token, get_task_max_token
)


# ================= 修复：工具调用及扫描效果组件 =================
class ToolCallWidget(Vertical):
    def __init__(self, tool_name: str, arguments: dict):
        super().__init__()
        self.tool_name = tool_name
        self.arguments = arguments
        self._scanning = True
        self._scan_pos = 0
        
        # 💡 修复1：在 __init__ 中提前实例化 scan_label 
        # 避免历史记录瞬间加载时，compose 还未执行就被 finish() 访问导致 AttributeError 卡死 
        self.scan_label = Static("  ⠋ 正在执行...", classes="tool-scanning")

    def compose(self) -> ComposeResult:
        args_str = json.dumps(self.arguments, ensure_ascii=False)
        yield Static(f"{self.tool_name}({args_str})", classes="tool-header")
        # 直接 yield 已经在 __init__ 里实例化好的组件
        yield self.scan_label

    def on_mount(self):
        self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        if self._scanning:
            self._timer = self.set_interval(0.1, self._update_scan)

    def _update_scan(self):
        if self._scanning:
            self._scan_pos = (self._scan_pos + 1) % len(self._frames)
            self.scan_label.update(f"  {self._frames[self._scan_pos]} 正在执行...")

    def finish(self, result: str):
        self._scanning = False
        if hasattr(self, "_timer"):
            self._timer.stop()

        # 💡 修复2：增加针对历史记录中 content 为 None 的空值容错，防止 strip() 再次引发崩溃
        if not result:
            result = "执行完毕"

        # 提取时间戳，不显示完整结果
        import re
        timestamp_match = re.search(r'\[finish at ([^\]]+)\]', str(result))
        if timestamp_match:
            formatted_result = f"    └── [Finish at {timestamp_match.group(1)}]"
        else:
            # 如果没有找到时间戳，显示简化的完成信息
            formatted_result = "    └── Finish"

        # 此时即便还未上屏，update() 也能安全修改内部缓存的内容，渲染时直接就是完成态
        self.scan_label.update(formatted_result)
        self.scan_label.remove_class("tool-scanning")
        self.scan_label.add_class("tool-result")


# ================= 修复：支持真实流式渲染的气泡 =================
class ChatMessage(Vertical):
    def __init__(self, role: str, text: str, is_new: bool = False):
        super().__init__()
        self.role = role
        self.text = text
        self.is_new = is_new
        self.add_class(role)
        self._typing_timer = None
        self._current_text = ""
        self._target_text = text
        self._typing_index = 0

    def compose(self) -> ComposeResult:
        if self.role == "user":
            yield Static("> User", classes="role-user")
            yield Markdown(self.text)
        elif self.role == "assistant":
            yield Static("● CatInCup", classes="role-ai")
            if self.text and str(self.text).strip():
                self.md_widget = Markdown(self.text)
                yield self.md_widget
            else:
                # 当content为空时，不创建任何组件，避免空白占位
                self.md_widget = None

    def on_mount(self):
        if self.role == "assistant":
            if self.text == "" and self.is_new:
                # 只有新消息且content为空时，才显示加载spinner
                # 历史记录中content为空的情况不显示spinning
                if self.md_widget:
                    self.md_widget.update("⠋")
                    self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                    self._frame_index = 0
                    self._spinner_timer = self.set_interval(0.1, self._update_spinner)
            elif self.is_new and self.text and str(self.text).strip():
                # 只有新消息且有内容时才启动打字机效果
                self._start_typing()

    def _update_spinner(self):
        if hasattr(self, "md_widget"):
            self.md_widget.update(self._frames[self._frame_index])
            self._frame_index = (self._frame_index + 1) % len(self._frames)

    def _start_typing(self):
        if hasattr(self, "_spinner_timer"):
            self._spinner_timer.stop()
        self._current_text = ""
        self._target_text = self.text
        self._typing_index = 0
        if self._typing_timer:
            self._typing_timer.stop()
        self._typing_timer = self.set_interval(0.05, self._type_next_char)

    def _type_next_char(self):
        if self._typing_index < len(self._target_text):
            self._current_text += self._target_text[self._typing_index]
            self._typing_index += 1
            if hasattr(self, "md_widget"):
                self.md_widget.update(self._current_text)
        else:
            if self._typing_timer:
                self._typing_timer.stop()

    def update_content(self, new_text: str):
        if self.role == "assistant":
            self.text = new_text
            self._target_text = new_text
            if self._typing_timer:
                self._typing_timer.stop()
            # 只有当有内容时才启动打字机效果
            if new_text and str(new_text).strip():
                # 如果当前没有md_widget或是Static组件，替换为Markdown组件
                if not hasattr(self, "md_widget") or self.md_widget is None or isinstance(self.md_widget, Static):
                    if hasattr(self, "md_widget") and self.md_widget:
                        # 移除旧的组件
                        self.md_widget.remove()
                    # 创建新的Markdown组件
                    self.md_widget = Markdown(new_text)
                    # 挂载新组件
                    self.mount(self.md_widget)
                # 启动打字机效果
                self._start_typing()


# ================= 修复：完美还原 WebUI 的输入框 =================
class ChatInput(TextArea):
    """还原 WebUI 体验：Enter 发送，Shift+Enter 换行"""

    def on_key(self, event: Key) -> None:
        if event.key == "enter":
            # 阻止默认换行，执行发送
            event.prevent_default()
            text = self.text.strip()
            if text:
                self.app.query_one(MainView).handle_chat_submit(text)
                self.clear()
        elif event.key in ["shift+enter", "alt+enter"]:
            # 阻止发送，在光标处插入原生换行符
            event.prevent_default()
            self.insert("\n")


# ================= 修复：补全工具挂载逻辑的主视图 =================
class MainView(Horizontal):
    # [保留原有的 compose, on_mount, on_event, blink_cat 逻辑不变]
    def compose(self) -> ComposeResult:
        # ======= 左侧区域 =======
        with Vertical(id="left-pane"):
            with Horizontal(id="top-zone"):
                yield Static("  /\\_/\\\n ( o.o )\n  > ^ <", id="cat-ascii")
                with Vertical(id="status-container"):
                    yield Static("Cat-in-Cup v1.0.0", id="version-text")
                    yield ProgressBar(total=100, show_eta=False, id="token-progress")

            chat_zone = VerticalScroll(id="chat-zone")
            chat_zone.border_title = "Chat History /"
            yield chat_zone

            input_zone = Vertical(id="input-zone")
            input_zone.border_title = "Chat Input /"
            with input_zone:
                with Horizontal(id="input-row"):
                    yield Static("❯", id="prompt-char")
                    yield ChatInput(id="chat-input", show_line_numbers=False)

        # ======= 右侧区域 =======
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
        self.rendered_msg_counts = {"nav-main": 0}
        self.tool_widgets = {}
        self.query_one("#chat-input", ChatInput).focus()
        self.set_interval(3.0, self.blink_cat)
        self.set_interval(1.0, self.refresh_chat_state)

    async def on_event(self, event: Event) -> None:
        self.last_activity_time = time.time()
        await super().on_event(event)

    def blink_cat(self) -> None:
        cat = self.query_one("#cat-ascii", Static)
        idle_time = time.time() - self.last_activity_time
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
        self.current_space = event.item.id
        chat_zone = self.query_one("#chat-zone")
        for child in chat_zone.children:
            child.remove()
        self.rendered_msg_counts[self.current_space] = 0
        self.tool_widgets.clear()
        self.refresh_chat_state()

    def handle_chat_submit(self, text: str):
        if self.current_space == "nav-main":
            force_push_agent(text)
        else:
            task_id = self.current_space.replace("task-", "")
            force_push_task(task_id, text)

        # 不直接挂载消息，让refresh_chat_state来处理
        # 这样可以避免重复显示消息
        chat_zone = self.query_one("#chat-zone")
        chat_zone.scroll_end(animate=False)

    def refresh_chat_state(self):
        tasks = get_task_list()
        sidebar = self.query_one("#sidebar-nav", ListView)
        existing_ids = [item.id for item in sidebar.children if item.id]

        for task in tasks:
            task_list_id = f"task-{task['id']}"
            if task_list_id not in existing_ids:
                new_item = ListItem(Static(f"{task['name']}", classes="nav-item"), id=task_list_id)
                sidebar.append(new_item)
                if task_list_id not in self.rendered_msg_counts:
                    self.rendered_msg_counts[task_list_id] = 0

        if self.current_space == "nav-main":
            history = get_agent_history()
            current_token = get_window_token()
            max_token = get_agent_max_token()
        else:
            task_id = self.current_space.replace("task-", "")
            history = get_task_history(task_id)
            current_token = get_task_window_token(task_id)
            max_token = get_task_max_token()

        progress = self.query_one("#token-progress", ProgressBar)
        progress.total = max_token
        progress.update(progress=min(current_token, max_token))

        chat_zone = self.query_one("#chat-zone")
        rendered_count = self.rendered_msg_counts.get(self.current_space, 0)
        visible_history = [msg for msg in history if msg.get("role") != "system"]

        # === 修复：热更新时动态捕获大模型追加的 tool_calls ===
        # 💡 安全锁：只有当没有未渲染的新消息时，才允许更新屏幕上最后一个气泡
        # 防止流式输出“找错目标”强行覆盖旧气泡，导致双重渲染（两个一模一样的东西）
        if visible_history and rendered_count > 0 and len(visible_history) <= rendered_count:
            last_data = visible_history[-1]
            if last_data.get("role") == "assistant":
                chat_msgs = list(chat_zone.query(ChatMessage))
                if chat_msgs:
                    last_widget = chat_msgs[-1]
                    if last_widget.role == "assistant":
                        new_content = last_data.get("content", "")
                        if last_widget.text != new_content:
                            last_widget.update_content(new_content)
                            chat_zone.scroll_end(animate=False)

                        # 【关键】抓取流式输出末尾新增的函数调用并挂载
                        tool_calls = last_data.get("tool_calls", [])
                        for tc in tool_calls:
                            tc_id = tc.get("id")
                            if tc_id not in self.tool_widgets:
                                func = tc.get("function", {})
                                name = func.get("name", "")
                                args_str = func.get("arguments", "{}")
                                try:
                                    args = json.loads(args_str)
                                except Exception:
                                    args = {"raw_args": args_str}

                                tw = ToolCallWidget(name, args)
                                self.tool_widgets[tc_id] = tw
                                chat_zone.mount(tw)
                                chat_zone.scroll_end(animate=False)

        # 增量挂载新消息
        if len(visible_history) > rendered_count:
            # 判断是否是初始化加载历史消息
            is_initial_load = rendered_count == 0
            
            for msg in visible_history[rendered_count:]:
                role = msg.get("role")
                content = msg.get("content", "")

                if role == "user":
                    # 用户消息不需要打字机效果
                    chat_zone.mount(ChatMessage("user", content, is_new=False))

                elif role == "assistant":
                    # 无论是否是初始化加载，只要是assistant消息，就挂载ChatMessage
                    # 这样可以确保工具调用的assistant消息也能显示·CatInCup角色标识
                    # 空content的情况由ChatMessage内部处理，只显示角色标识
                    is_new_msg = not is_initial_load
                    chat_zone.mount(ChatMessage("assistant", content, is_new=is_new_msg))

                    # 无论有没有普通文本，工具调用都要照常解析和挂载
                    tool_calls = msg.get("tool_calls", [])
                    for tc in tool_calls:
                        tc_id = tc.get("id")
                        if tc_id not in self.tool_widgets:
                            func = tc.get("function", {})
                            name = func.get("name", "")
                            args_str = func.get("arguments", "{}")
                            try:
                                args = json.loads(args_str)
                            except Exception:
                                args = {"raw_args": args_str}

                            tw = ToolCallWidget(name, args)
                            self.tool_widgets[tc_id] = tw
                            chat_zone.mount(tw)

                elif role == "tool":
                    tc_id = msg.get("tool_call_id")
                    tool_name = msg.get("name")  # 后端可能带有 name 字段
                    
                    tw = self.tool_widgets.get(tc_id)
                    
                    # 容错：如果 ID 没匹配上，尝试模糊匹配尚未完成的工具
                    if not tw:
                        for widget in self.tool_widgets.values():
                            if widget._scanning:
                                if tool_name and widget.tool_name == tool_name:
                                    tw = widget
                                    break
                                elif not tool_name:
                                    # 连 name 都没有时，按顺序消耗第一个还在 scanning 的工具
                                    tw = widget
                                    break
                    
                    if tw:
                        tw.finish(content)
                    else:
                        # 只有当找不到任何正在执行的对应工具时，才追加在最后
                        fallback_msg = f"   └── {content}"
                        chat_zone.mount(Static(fallback_msg, classes="tool-result"))

            self.rendered_msg_counts[self.current_space] = len(visible_history)
            chat_zone.scroll_end(animate=False)
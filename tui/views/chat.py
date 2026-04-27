import time
import json
from textual import work, on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Static, Markdown, ProgressBar, ListView, ListItem, TextArea
from textual.events import Event, Key

from src.harness import task as task_module
from tui.api import (
    get_task_list, get_agent_history, get_task_history, force_push_agent, force_push_task,
    flush_agent_memory,
    get_window_token, get_task_window_token, get_agent_max_token, get_task_max_token,
    format_task_log
)
from textual.screen import ModalScreen


# ================= 工具调用及扫描效果组件 (保持不变) =================
class ToolCallWidget(Vertical):
    def __init__(self, tool_name: str, arguments: dict):
        super().__init__()
        self.tool_name = tool_name
        self.arguments = arguments
        self._scanning = True
        self._scan_pos = 0
        self.scan_label = Static("  ⠋ 正在执行...", classes="tool-scanning")

    def compose(self) -> ComposeResult:
        args_str = json.dumps(self.arguments, ensure_ascii=False)
        # 禁用标记语言解析，避免代码内容被错误解析
        yield Static(f"{self.tool_name}({args_str})", classes="tool-header", markup=False)
        yield self.scan_label

    def on_mount(self):
        self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        if self._scanning:
            self._timer = self.set_interval(0.1, self._update_scan)

    def _update_scan(self):
        if self._scanning and self.is_mounted: # 🟢 增加 is_mounted 保护
            self._scan_pos = (self._scan_pos + 1) % len(self._frames)
            try:
                self.scan_label.update(f"  {self._frames[self._scan_pos]} 正在执行...")
            except Exception:
                pass

    def finish(self, result: str):
        self._scanning = False
        if hasattr(self, "_timer"):
            self._timer.stop()

        if not result:
            result = "执行完毕"

        import re
        timestamp_match = re.search(r'\[finish at ([^\]]+)\]', str(result))
        if timestamp_match:
            formatted_result = f"    └── [Finish at {timestamp_match.group(1)}]"
        else:
            formatted_result = "    └── Finish"

        self.scan_label.update(formatted_result)
        self.scan_label.remove_class("tool-scanning")
        self.scan_label.add_class("tool-result")


# ================= 支持真实流式渲染的气泡 (保持不变) =================
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
            yield Static("● PurrCat", classes="role-ai")
            if self.text and str(self.text).strip():
                self.md_widget = Markdown(self.text)
                yield self.md_widget
            else:
                self.md_widget = None

    def on_mount(self):
        if self.role == "assistant":
            if self.text == "" and self.is_new:
                if self.md_widget:
                    self.md_widget.update("⠋")
                    self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                    self._frame_index = 0
                    self._spinner_timer = self.set_interval(0.1, self._update_spinner)
            elif self.is_new and self.text and str(self.text).strip():
                self._start_typing()

    def _update_spinner(self):
        if hasattr(self, "md_widget") and self.is_mounted: # 🟢 增加 is_mounted 保护
            try:
                self.md_widget.update(self._frames[self._frame_index])
                self._frame_index = (self._frame_index + 1) % len(self._frames)
            except Exception:
                pass

    def _start_typing(self):
        if hasattr(self, "_spinner_timer"):
            self._spinner_timer.stop()
        self._current_text = ""
        self._target_text = self.text
        self._typing_index = 0
        if self._typing_timer:
            self._typing_timer.stop()
        # 🟢 修复：将刷新率降至合理的 15ms (约 60fps)，释放事件循环
        self._typing_timer = self.set_interval(0.015, self._type_next_char)

    def _type_next_char(self):
        # 🟢 修复：每次打印 3 个字符，既能保持飞快的视觉速度，又大幅减少 DOM 渲染次数
        chunk_size = 3
        if self._typing_index < len(self._target_text):
            self._current_text += self._target_text[self._typing_index : self._typing_index + chunk_size]
            self._typing_index += chunk_size
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
            if new_text and str(new_text).strip():
                if not hasattr(self, "md_widget") or self.md_widget is None or isinstance(self.md_widget, Static):
                    if hasattr(self, "md_widget") and self.md_widget:
                        self.md_widget.remove()
                    self.md_widget = Markdown(new_text)
                    self.mount(self.md_widget)
                self._start_typing()


# ================= 拦截 /switch 指令 =================
class ChatInput(TextArea):

    def on_mount(self) -> None:
        try:
            self.soft_wrap = True
        except AttributeError:
            pass

    async def on_key(self, event: Key) -> None:
        if event.key == "ctrl+o":
            event.prevent_default()
            self.insert("\n")
        elif event.key == "enter":
            event.prevent_default()
            text = self.text.strip()
            if text == "/switch":
                await self.app.query_one(MainView).show_space_selector()
                self.clear()
            elif text == "/config":
                await self.app.query_one(MainView).show_config_selector()
                self.clear()
            elif text == "/help":
                await self.app.query_one(MainView).show_help_guide()
                self.clear()
            elif text == "/flush":
                chat_zone = self.app.query_one(MainView).query_one("#chat-zone")
                status = Markdown("⏳ 正在压缩主 Agent 记忆，请稍候...", classes="help-message")
                chat_zone.mount(status)
                chat_zone.scroll_end(animate=False)
                self.clear()
                # 触发记忆压缩
                success = flush_agent_memory()
                if success:
                    status.update("✅ 主 Agent 记忆压缩完成，早期对话已归档。")
                else:
                    status.update("❌ 记忆压缩失败：Agent 未初始化")
            elif text:
                self.app.query_one(MainView).handle_chat_submit(text)
                self.clear()


# ================= 主视图：去掉侧边栏，改为 List 选择 =================
class MainView(Vertical):
    RAINBOW_COLORS = [
        {"id": "theme-white", "name": "默认 (White)", "color": "#ffffff"},
        {"id": "theme-red", "name": "绯红 (Red)", "color": "#ef4444"},
        {"id": "theme-orange", "name": "橘黄 (Orange)", "color": "#f97316"},
        {"id": "theme-yellow", "name": "明黄 (Yellow)", "color": "#eab308"},
        {"id": "theme-green", "name": "翠绿 (Green)", "color": "#22c55e"},
        {"id": "theme-cyan", "name": "青色 (Cyan)", "color": "#06b6d4"},
        {"id": "theme-blue", "name": "蔚蓝 (Blue)", "color": "#3b82f6"},
        {"id": "theme-purple", "name": "紫罗兰 (Purple)", "color": "#a855f7"},
        {"id": "theme-pink", "name": "猛男粉 (Pink)", "color": "#ec4899"},
    ]
    def compose(self) -> ComposeResult:
        with Vertical(id="left-pane"):
            top_zone = Horizontal(id="top-zone")
            top_zone.border_title = "PurrCat v1.0.0 /"
            with top_zone:
                yield Static("  /\\_/\\\n ( O_O )\n  |>  <|⟆", id="cat-ascii")
                with Vertical(id="status-container"):
                    yield Static("Token Window: [░░░░░░░░░░░░░░░░] 0%", id="token-progress")
            chat_zone = VerticalScroll(id="chat-zone")
            chat_zone.border_title = "Chat History /"
            yield chat_zone

            space_selector = ListView(id="space-selector")
            space_selector.border_title = "Select Space (Use Up/Down to Navigate, Enter to Select) /"
            yield space_selector

            # 🟢 新增：将配置选择器渲染到 DOM 中
            config_selector = ListView(id="config-selector")
            config_selector.border_title = "Theme Config (Select a color) /"
            yield config_selector

            # 📖 Guide Book
            help_guide = VerticalScroll(id="help-guide")
            help_guide.border_title = "Guide Book /"
            help_guide.can_focus = True
            yield help_guide

            input_zone = Vertical(id="input-zone")
            input_zone.border_title = "Chat Input (Ctrl+o for new line, /switch to change space) /"
            with input_zone:
                with Horizontal(id="input-row"):
                    yield Static("❯", id="prompt-char")
                    yield ChatInput(id="chat-input", show_line_numbers=False)

    def key_escape(self) -> None:
        """Escape 退出 Guide Book"""
        if self.is_selecting:
            self.hide_help_guide()

    def on_mount(self) -> None:
        self.current_space = "nav-main"
        self.last_activity_time = time.time()
        self.blink_state = False
        self.is_selecting = False
        self.rendered_msg_counts = {"nav-main": 0}
        self.tool_widgets = {}
        self._task_switch_pending = False

        self.query_one("#chat-input", ChatInput).focus()
        self.set_interval(0.25, self.blink_cat)
        self.set_interval(1.0, self.refresh_chat_state)

    async def on_event(self, event: Event) -> None:
        self.last_activity_time = time.time()
        await super().on_event(event)

    def blink_cat(self) -> None:
        cat = self.query_one("#cat-ascii", Static)
        idle_time = time.time() - self.last_activity_time
        if idle_time > 30:
            cat.update(" /\\_/\\ zZ\n( u_u )\n  |>  <|⟆")
        else:
            if not hasattr(self, "_blink_state"):
                self._blink_state = 0
                self._blink_counter = 0
                self._blink_duration = [5, 1, 1]
            if self._blink_state == 0:
                cat.update("  /\\_/\\\n ( O_O )\n  |>  <|⟆")
            elif self._blink_state == 1:
                cat.update("  /\\_/\\\n ( O_O )\n  |>  <|⟆")
            else:
                cat.update("  /\\_/\\\n ( -_- )\n  |>  <|⟆")
            self._blink_counter += 1
            if self._blink_counter >= self._blink_duration[self._blink_state]:
                self._blink_counter = 0
                self._blink_state = (self._blink_state + 1) % 3

    async def show_space_selector(self) -> None:
        self.is_selecting = True

        chat_zone = self.query_one("#chat-zone")
        space_selector = self.query_one("#space-selector")

        chat_zone.add_class("hidden")
        space_selector.add_class("active")
        self.query_one("#config-selector").remove_class("active")
        await space_selector.clear()

        space_selector.append(ListItem(Static("Main Space", classes="nav-item"), id="nav-main"))
        tasks = get_task_list()
        for task in tasks:
            space_selector.append(
                ListItem(Static(f"Task: {task['name']}", classes="nav-item"), id=f"task-{task['id']}"))

        space_selector.focus()

    async def show_config_selector(self) -> None:
        self.is_selecting = True
        chat_zone = self.query_one("#chat-zone")
        space_selector = self.query_one("#space-selector")
        config_selector = self.query_one("#config-selector")

        chat_zone.add_class("hidden")
        space_selector.remove_class("active")
        config_selector.add_class("active")

        await config_selector.clear()

        for color_option in self.RAINBOW_COLORS:
            config_selector.append(
                ListItem(Static(color_option["name"], classes="nav-item"), id=color_option["id"])
            )
        config_selector.focus()

    async def show_help_guide(self) -> None:
        self.is_selecting = True
        chat_zone = self.query_one("#chat-zone")
        space_selector = self.query_one("#space-selector")
        config_selector = self.query_one("#config-selector")
        help_guide = self.query_one("#help-guide")

        chat_zone.add_class("hidden")
        space_selector.remove_class("active")
        config_selector.remove_class("active")
        help_guide.add_class("active")

        # 🟢 修复：将 await help_guide.clear() 替换为安全的子节点移除方法
        for child in list(help_guide.children):
            child.remove()

        help_text = (
            "# 📖 PurrCat 使用指南\n\n"
            "## 命令\n"
            "| 命令 | 说明 |\n"
            "|------|------|\n"
            "| `/help` | 打开本指南 |\n"
            "| `/flush` | 强制压缩主 Agent 记忆，归档早期对话 |\n"
            "| `/switch` | 切换聊天空间（主 Agent / 子任务） |\n"
            "| `/config` | 切换主题配置 |\n"
            "\n"
            "## 快捷键\n"
            "- `Enter` — 发送消息\n"
            "- `Ctrl+O` — 换行\n"
            "- `Ctrl+Q` — 退出程序\n"
            "- `Escape` — 返回聊天（在 Guide Book 中）\n"
            "\n"
            "## 关于\n"
            "PurrCat — 终端里的 AI 聊天猫 🐱"
        )
        help_guide.mount(Markdown(help_text))
        help_guide.scroll_end(animate=False)
        help_guide.focus()

    @on(ListView.Selected, "#space-selector")
    def switch_space(self, event: ListView.Selected):
        self.current_space = event.item.id
        self.is_selecting = False

        chat_zone = self.query_one("#chat-zone")
        space_selector = self.query_one("#space-selector")

        space_selector.remove_class("active")
        chat_zone.remove_class("hidden")
        self.query_one("#chat-input").focus()

        # 🟢 终极修复：彻底抛弃 remove_children()！用显示/隐藏代替销毁/重建
        if self.current_space == "nav-main":
            # 切回 Main：隐藏所有 Task 的组件，显示 Main 的组件
            for child in chat_zone.children:
                if child.id and str(child.id).startswith("task-log-widget"):
                    child.display = False
                else:
                    child.display = True
            chat_zone.scroll_end(animate=False)
        else:
            # 切到 Task：隐藏主空间的聊天气泡
            for child in chat_zone.children:
                if not (child.id and str(child.id).startswith("task-log-widget")):
                    child.display = False
                else:
                    child.display = True
            # 标记需要强制刷新日志
            self._task_switch_pending = True

        # ⚠️ 极其重要：删掉原本清空 rendered_msg_counts 和 tool_widgets 的两行代码！
        # 让 nav-main 记住它已经渲染了多少条消息，切回来时直接复用，绝不从头渲染！
        
        self.refresh_chat_state()

    # 🟢 新增：捕获菜单选择并动态修改整个 TUI 的边框颜色
    @on(ListView.Selected, "#config-selector")
    def switch_theme(self, event: ListView.Selected):
        selected_id = event.item.id
        
        # 🟢 修复：从预设表中根据 ID 查找对应的颜色 Hex 值
        color_hex = "#ffffff" # 默认值
        for option in self.RAINBOW_COLORS:
            if option["id"] == selected_id:
                color_hex = option["color"]
                break

        self.is_selecting = False
        chat_zone = self.query_one("#chat-zone")
        config_selector = self.query_one("#config-selector")

        config_selector.remove_class("active")
        chat_zone.remove_class("hidden")
        self.query_one("#chat-input").focus()

        # 动态修改边框颜色
        zones = ["#top-zone", "#chat-zone", "#space-selector", "#config-selector", "#input-zone"]
        for zone_id in zones:
            try:
                widget = self.query_one(zone_id)
                widget.styles.border = ("round", color_hex)
                widget.styles.border_title_color = color_hex
            except Exception:
                pass

        self.refresh_chat_state()

    def handle_chat_submit(self, text: str):
        if self.current_space == "nav-main":
            force_push_agent(text)
        else:
            task_id = self.current_space.replace("task-", "")
            force_push_task(task_id, text)

        chat_zone = self.query_one("#chat-zone")
        chat_zone.scroll_end(animate=False)

    def hide_help_guide(self) -> None:
        self.is_selecting = False
        chat_zone = self.query_one("#chat-zone")
        help_guide = self.query_one("#help-guide")
        help_guide.remove_class("active")
        chat_zone.remove_class("hidden")
        self.query_one("#chat-input").focus()

    # 🟢 修复：在 def 前加上 async，Textual 的 set_interval 原生支持异步回调
    async def refresh_chat_state(self):
        if self.is_selecting:
            return

        if self.current_space == "nav-main":
            current_token = get_window_token()
            max_token = get_agent_max_token()
        else:
            task_id = self.current_space.replace("task-", "")
            current_token = get_task_window_token(task_id)
            max_token = get_task_max_token()

        progress = self.query_one("#token-progress", Static)
        percentage = (current_token / max_token * 100) if max_token > 0 else 0

        progress.remove_class("token-low", "token-medium", "token-high")
        if percentage <= 60:
            progress.add_class("token-low")
        elif percentage <= 90:
            progress.add_class("token-medium")
        else:
            progress.add_class("token-high")

        filled = int(percentage / 5)
        bar = "█" * filled + "░" * (20 - filled)
        progress.update(f"Token Window: [{bar}] {int(percentage)}%")

        chat_zone = self.query_one("#chat-zone")

        # ================= 结合 Dirty Task 的极致优化 =================
        if self.current_space != "nav-main":
            task_id = self.current_space.replace("task-", "")
            widget_id = f"task-log-widget-{task_id}"
            
            needs_update = False
            log_widget = None

            # 1. 判断是否是刚切进来（DOM里还没这个任务的 Widget）
            try:
                log_widget = chat_zone.query_one(f"#{widget_id}", Static)
            except Exception:
                needs_update = True  # 没找到说明是首次渲染
            
            # 2. 检查内存中的 Dirty 标记 (O(1) 极速操作)
            with task_module.task_set_lock:
                if task_id in task_module.dirty_tasks:
                    needs_update = True
                    # 消费掉这个 dirty 标记，代表 UI 已经知晓并准备更新
                    task_module.dirty_tasks.remove(task_id)

            # 3. 如果是刚切换过来，强制刷新
            if getattr(self, '_task_switch_pending', False):
                needs_update = True
                self._task_switch_pending = False

            # 🎈 核心拦截：如果没变脏，且不是首次渲染，直接退出！无磁盘 IO，无 DOM 操作！
            if not needs_update:
                return

            # 🟢 修复：使用 asyncio.to_thread 将同步读盘操作移出 UI 主线程！
            import asyncio
            log_content = await asyncio.to_thread(format_task_log, task_id)

            # 4. 挂载或更新 UI — 用 Markdown 渲染，比纯文本好看
            if log_widget:
                log_widget.update(log_content)
                log_widget.display = True
            else:
                # 🟢 修复：将 markup=False 改为 True，并加上一点内边距让文字不贴边
                new_widget = Static(log_content, id=widget_id, markup=True)
                new_widget.styles.padding = (1, 2)
                chat_zone.mount(new_widget)
            
            chat_zone.scroll_end(animate=False)
            return
        # ================================================================

        history = get_agent_history()
        rendered_count = self.rendered_msg_counts.get(self.current_space, 0)
        visible_history = [msg for msg in history if msg.get("role") != "system"]
        
        # 🟢 修复 3.1：清理时，绝不遍历所有 children，只精准清理当前空间带有专属标签的节点
        if rendered_count > 0 and len(visible_history) < rendered_count:
            # 说明触发了 /flush，历史记录变短了，只清理当前空间的消息
            for child in chat_zone.query(f".msg-space-{self.current_space}"):
                child.remove()
            self.tool_widgets.clear()
            self.rendered_msg_counts[self.current_space] = 0
            rendered_count = 0
            
        if visible_history and rendered_count > 0 and len(visible_history) <= rendered_count:
            last_data = visible_history[-1]
            if last_data.get("role") == "assistant":
                # 🟢 修复 3.2：精准查询当前空间的 ChatMessage，大幅提升查询速度，防止串线
                chat_msgs = list(chat_zone.query(f"ChatMessage.msg-space-{self.current_space}"))
                if chat_msgs:
                    last_widget = chat_msgs[-1]
                    if last_widget.role == "assistant":
                        new_content = last_data.get("content", "")
                        if last_widget.text != new_content:
                            last_widget.update_content(new_content)
                            chat_zone.scroll_end(animate=False)

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
                                tw.add_class(f"msg-space-{self.current_space}") # 🟢 打上空间标签
                                self.tool_widgets[tc_id] = tw
                                chat_zone.mount(tw)
                                chat_zone.scroll_end(animate=False)

        if len(visible_history) > rendered_count:
            is_initial_load = rendered_count == 0
            for msg in visible_history[rendered_count:]:
                role = msg.get("role")
                content = msg.get("content", "")

                if role == "user":
                    new_msg = ChatMessage("user", content, is_new=False)
                    new_msg.add_class(f"msg-space-{self.current_space}") # 🟢 打上空间标签
                    chat_zone.mount(new_msg)

                elif role == "assistant":
                    is_new_msg = not is_initial_load
                    new_msg = ChatMessage("assistant", content, is_new=is_new_msg)
                    new_msg.add_class(f"msg-space-{self.current_space}") # 🟢 打上空间标签
                    chat_zone.mount(new_msg)

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
                            tw.add_class(f"msg-space-{self.current_space}") # 🟢 打上空间标签
                            self.tool_widgets[tc_id] = tw
                            chat_zone.mount(tw)

                elif role == "tool":
                    tc_id = msg.get("tool_call_id")
                    tool_name = msg.get("name")
                    tw = self.tool_widgets.get(tc_id)

                    if not tw:
                        for widget in self.tool_widgets.values():
                            if widget._scanning:
                                if tool_name and widget.tool_name == tool_name:
                                    tw = widget
                                    break
                                elif not tool_name:
                                    tw = widget
                                    break

                    if tw:
                        tw.finish(content)
                    else:
                        fallback_msg = f"   └── {content}"
                        fb_widget = Static(fallback_msg, classes="tool-result")
                        fb_widget.add_class(f"msg-space-{self.current_space}") # 🟢 打上空间标签
                        chat_zone.mount(fb_widget)

            self.rendered_msg_counts[self.current_space] = len(visible_history)
            chat_zone.scroll_end(animate=False)
# ================= Task Monitor Screen =================

class TaskMonitorScreen(ModalScreen):
    def __init__(self):
        super().__init__()
        self.selected_task = None
        self.showing_log = False

    def compose(self) -> ComposeResult:
        with Vertical(id="task-dialog"):
            yield Static("Task Monitor — PurrCat Background Tasks", id="task-dialog-header")
            yield VerticalScroll(id="task-dialog-list")
            yield Static("Ctrl+q: Close  |  Enter: View Logs  |  Esc: Back", id="task-dialog-footer")

    def on_mount(self):
        self.refresh_task_list()

    def refresh_task_list(self):
        task_list = self.query_one("#task-dialog-list")
        # 安全清空子节点
        for child in list(task_list.children):
            child.remove()
            
        tasks = get_task_list()
        if not tasks:
            task_list.mount(Static("No active tasks.", classes="task-detail"))
            return
            
        for t in tasks:
            state = t.get("state", "unknown")
            state_emoji = {"running": "🟢", "done": "🔵", "error": "🔴", "waiting": "🟡"}.get(state, "⚪")
            
            # 1. 先单独创建好所有的子组件
            name = Static(f"{state_emoji}  {t.get('name', '?')}", classes="task-name")
            state_label = Static(f"State: {state}", classes="task-state " + state)
            
            expert = t.get("expert_type", "?")
            step = t.get("step", 0)
            tokens = t.get("token_usage", 0)
            created = t.get("create_time", "")
            if isinstance(created, (int, float)):
                import datetime
                created = datetime.datetime.fromtimestamp(created).strftime("%H:%M:%S")
                
            detail = Static(
                f"  ID: {str(t['id'])[:16]}... | Type: {expert} | Step: {step} | Tokens: {tokens} | {created}",
                classes="task-detail"
            )
            
            # 🟢 修复：在实例化 Vertical 容器时，直接把刚才创建的子组件当作参数塞进去！
            card = Vertical(
                name,
                state_label,
                detail,
                classes="task-card",
                id=f"task-card-{t['id']}"
            )
            
            # 2. 将已经包含所有子组件的 card，一次性挂载到列表中
            task_list.mount(card)


    def view_task_log(self, task_id):
        self.selected_task = task_id
        self.showing_log = True
        task_list = self.query_one("#task-dialog-list")
        
        # 安全清空子节点
        for child in list(task_list.children):
            child.remove()

        log_text = format_task_log(task_id)
        
        # 1. 🟢 修复：先用列表推导式，把所有的日志行组件单独创建出来
        log_entries = [
            Static(line, classes="log-entry", markup=True)
            for line in log_text.split("\n")
        ]
        
        # 2. 🟢 修复：在实例化 VerticalScroll 时，使用 *log_entries 解包把子组件直接传进去！
        log_viewer = VerticalScroll(*log_entries, id="task-log-viewer")
        
        # 3. 最后将整个装满日志的容器挂载到大盘上
        task_list.mount(log_viewer)
        log_viewer.focus()

    def key_escape(self):
        if self.showing_log:
            self.showing_log = False
            self.refresh_task_list()
        else:
            self.app.pop_screen()

    def key_enter(self):
        if not self.showing_log:
            # View log of first visible task in list
            import re
            cards = list(self.query(".task-card"))
            if cards:
                for c in cards:
                    if c.id and c.id.startswith("task-card-"):
                        task_id = c.id.replace("task-card-", "")
                        self.view_task_log(task_id)
                        break

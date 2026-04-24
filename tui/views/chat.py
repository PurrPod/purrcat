import time
import json
from textual import work, on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Static, Markdown, ProgressBar, ListView, ListItem, TextArea
from textual.events import Event, Key

from src.models import task as task_module
from tui.api import (
    get_task_list, get_agent_history, get_task_history, force_push_agent, force_push_task,
    get_window_token, get_task_window_token, get_agent_max_token, get_task_max_token,
    format_task_log
)


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
        yield Static(f"{self.tool_name}({args_str})", classes="tool-header")
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
            yield Static("● CatInCup", classes="role-ai")
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
        self._typing_timer = self.set_interval(0.005, self._type_next_char)

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

    # 🟢 1. 加上 async
    async def on_key(self, event: Key) -> None:
        if event.key == "ctrl+o":
            event.prevent_default()
            self.insert("\n")
        elif event.key == "enter":
            event.prevent_default()
            text = self.text.strip()
            if text == "/switch":
                # 🟢 2. 加上 await
                await self.app.query_one(MainView).show_space_selector()
                self.clear()
            # 🟢 新增：拦截 /config 指令
            elif text == "/config":
                await self.app.query_one(MainView).show_config_selector()
                self.clear()
            elif text:
                self.app.query_one(MainView).handle_chat_submit(text)
                self.clear()


# ================= 主视图：去掉侧边栏，改为 List 选择 =================
class MainView(Vertical):
    # 🟢 新增：彩虹颜色预设表
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
            top_zone.border_title = "CatInCup v1.0.0 /"
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

            input_zone = Vertical(id="input-zone")
            input_zone.border_title = "Chat Input (Ctrl+o for new line, /switch to change space) /"
            with input_zone:
                with Horizontal(id="input-row"):
                    yield Static("❯", id="prompt-char")
                    yield ChatInput(id="chat-input", show_line_numbers=False)

    def on_mount(self) -> None:
        self.current_space = "nav-main"
        self.last_activity_time = time.time()
        self.blink_state = False
        self.is_selecting = False
        self.rendered_msg_counts = {"nav-main": 0}
        self.tool_widgets = {}

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

    # 🟢 1. 加上 async
    async def show_space_selector(self) -> None:
        self.is_selecting = True

        chat_zone = self.query_one("#chat-zone")
        space_selector = self.query_one("#space-selector")

        chat_zone.add_class("hidden")
        space_selector.add_class("active")
        self.query_one("#config-selector").remove_class("active") # 🟢 新增：打开切换任务时，确保主题菜单关闭

        # 🟢 2. 加上 await！强制等待旧节点销毁完毕，避免 ID 冲突
        await space_selector.clear()

        space_selector.append(ListItem(Static("Main Space", classes="nav-item"), id="nav-main"))
        tasks = get_task_list()
        for task in tasks:
            space_selector.append(
                ListItem(Static(f"Task: {task['name']}", classes="nav-item"), id=f"task-{task['id']}"))

        space_selector.focus()

    # 🟢 新增：弹出主题颜色菜单
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
            # 切到 Task：只显示当前 Task 的组件，把 Main 的气泡全藏起来
            current_task_id = self.current_space.replace("task-", "")
            target_widget_id = f"task-log-widget-{current_task_id}"
            for child in chat_zone.children:
                if child.id == target_widget_id:
                    child.display = True
                else:
                    child.display = False

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

    def refresh_chat_state(self):
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

            # 🎈 核心拦截：如果没变脏，且不是首次渲染，直接退出！无磁盘 IO，无 DOM 操作！
            if not needs_update:
                return

            # 3. 只有确认需要更新时，才去读取并格式化磁盘日志
            log_content = format_task_log(task_id)

            # 4. 挂载或更新 UI
            if log_widget:
                # 已经是脏的了，直接全量塞进去即可
                log_widget.update(log_content)
                log_widget.display = True # 确保它可见
            else:
                # 🟢 修复：首次进入该 Task，直接 mount 挂载（千万不要清空容器了！）
                new_widget = Static(log_content, id=widget_id)
                chat_zone.mount(new_widget)
            
            chat_zone.scroll_end(animate=False)
            return
        # ================================================================

        history = get_agent_history()
        rendered_count = self.rendered_msg_counts.get(self.current_space, 0)
        visible_history = [msg for msg in history if msg.get("role") != "system"]

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

        if len(visible_history) > rendered_count:
            is_initial_load = rendered_count == 0
            for msg in visible_history[rendered_count:]:
                role = msg.get("role")
                content = msg.get("content", "")

                if role == "user":
                    chat_zone.mount(ChatMessage("user", content, is_new=False))

                elif role == "assistant":
                    is_new_msg = not is_initial_load
                    chat_zone.mount(ChatMessage("assistant", content, is_new=is_new_msg))

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
                        chat_zone.mount(Static(fallback_msg, classes="tool-result"))

            self.rendered_msg_counts[self.current_space] = len(visible_history)
            chat_zone.scroll_end(animate=False)
import time
import json
import asyncio
from textual import work, on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Static, Markdown, ListView, ListItem
from textual.events import Event, Key

from src.harness.process import Task as task_module
from tui.api import (
    get_task_list, get_agent_history, get_task_history, force_push_agent, force_push_task,
    get_window_token, get_task_window_token, get_agent_max_token, get_task_max_token,
    format_task_log,
    get_session_list, get_current_session_id, checkout_session
)
from src.utils.skill_helper import get_available_skills
from tui.views.chat_input import ChatInput
from tui.views.chat_message import ChatMessage
from tui.views.tool_call_widget import ToolCallWidget
from tui.views.utils import parse_events_content


class MainView(Vertical):
    RAINBOW_COLORS = [
        {"id": "theme-white", "name": "默认 (White)", "color": "#ffffff"},
        {"id": "theme-red", "name": "砖红 (Brick Red)", "color": "#bf616a"},
        {"id": "theme-orange", "name": "陶土 (Clay Orange)", "color": "#d08770"},
        {"id": "theme-yellow", "name": "柔麦 (Wheat Yellow)", "color": "#ebcb8b"},
        {"id": "theme-green", "name": "豆沙 (Sage Green)", "color": "#a3be8c"},
        {"id": "theme-cyan", "name": "冰霜 (Frost Cyan)", "color": "#88c0d0"},
        {"id": "theme-blue", "name": "雾霾 (Mist Blue)", "color": "#81a1c1"},
        {"id": "theme-purple", "name": "丁香 (Lilac Purple)", "color": "#b48ead"},
        {"id": "theme-pink", "name": "脏粉 (Dusty Pink)", "color": "#d3a5b4"},
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

            config_selector = ListView(id="config-selector")
            config_selector.border_title = "Theme Config (Select a color) /"
            yield config_selector

            session_selector = ListView(id="session-selector")
            session_selector.border_title = "Session Tree (Git Graph) /"
            yield session_selector

            # 🟢 新增技能选择器层
            skill_selector = ListView(id="skill-selector")
            skill_selector.border_title = "Select Skills (1: Mark, 0: Unmark, Enter: Confirm) /"
            yield skill_selector

            help_guide = VerticalScroll(id="help-guide")
            help_guide.border_title = "Guide Book /"
            help_guide.can_focus = True
            yield help_guide

            input_zone = Vertical(id="input-zone")
            input_zone.border_title = "Chat Input (Ctrl+o for new line, /help for help) /"
            with input_zone:
                with Horizontal(id="input-row"):
                    yield Static("❯", id="prompt-char")
                    yield ChatInput(id="chat-input", show_line_numbers=False)

    def key_escape(self) -> None:
        """Escape 退出各种 Overlay 界面"""
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

        # 记录已标记的技能
        self.marked_skills = set()

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

    # ===================== 全局键盘事件监听 =====================
    @on(Key)
    def handle_keys(self, event: Key) -> None:
        try:
            skill_selector = self.query_one("#skill-selector")
            # 只有在技能选择界面激活时，才拦截 1 和 0 按键
            if skill_selector.has_class("active"):
                if event.character == "1":
                    self.toggle_skill_mark(True)
                    event.prevent_default()
                elif event.character == "0":
                    self.toggle_skill_mark(False)
                    event.prevent_default()
        except Exception:
            pass

    def toggle_skill_mark(self, mark: bool) -> None:
        skill_selector = self.query_one("#skill-selector")
        highlighted_item = getattr(skill_selector, "highlighted_child", None)
        if not highlighted_item:
            return

        static = highlighted_item.query_one(Static)
        skill_name = getattr(static, "_skill_name", None)
        if not skill_name:
            return

        if mark:
            self.marked_skills.add(skill_name)
            static._original_text = f"[*] {skill_name}"
        else:
            self.marked_skills.discard(skill_name)
            static._original_text = f"[ ] {skill_name}"

        # 立即刷新当前高亮项的显示
        static.update(f"[bold cyan]>[/bold cyan] {static._original_text}")

    # ===================== 各类 Overlay 的显示逻辑 =====================
    async def show_space_selector(self) -> None:
        self.is_selecting = True

        chat_zone = self.query_one("#chat-zone")
        space_selector = self.query_one("#space-selector")

        chat_zone.add_class("hidden")
        self.query_one("#config-selector").remove_class("active")
        self.query_one("#session-selector").remove_class("active")
        self.query_one("#skill-selector").remove_class("active")
        self.query_one("#help-guide").remove_class("active")
        space_selector.add_class("active")

        await space_selector.clear()
        main_static = Static("  Main Space", classes="nav-item", markup=True)
        main_static._original_text = "Main Space"
        space_selector.append(ListItem(main_static, id="nav-main"))
        tasks = get_task_list()
        for task in tasks:
            task_name = f"Task: {task['name']}"
            task_static = Static(f"  {task_name}", classes="nav-item", markup=True)
            task_static._original_text = task_name
            space_selector.append(ListItem(task_static, id=f"task-{task['id']}"))

        space_selector.focus()

    async def show_config_selector(self) -> None:
        self.is_selecting = True
        chat_zone = self.query_one("#chat-zone")
        config_selector = self.query_one("#config-selector")

        chat_zone.add_class("hidden")
        self.query_one("#space-selector").remove_class("active")
        self.query_one("#session-selector").remove_class("active")
        self.query_one("#skill-selector").remove_class("active")
        self.query_one("#help-guide").remove_class("active")
        config_selector.add_class("active")

        await config_selector.clear()

        for color_option in self.RAINBOW_COLORS:
            opt_static = Static(f"  {color_option['name']}", classes="nav-item", markup=True)
            opt_static._original_text = color_option["name"]
            config_selector.append(ListItem(opt_static, id=color_option["id"]))
        config_selector.focus()

    async def show_session_selector(self) -> None:
        self.is_selecting = True
        chat_zone = self.query_one("#chat-zone")
        session_selector = self.query_one("#session-selector")

        chat_zone.add_class("hidden")
        self.query_one("#space-selector").remove_class("active")
        self.query_one("#config-selector").remove_class("active")
        self.query_one("#skill-selector").remove_class("active")
        self.query_one("#help-guide").remove_class("active")
        session_selector.add_class("active")

        await session_selector.clear()

        sessions = get_session_list()
        current_id = get_current_session_id()
        roots = [sid for sid, info in sessions.items() if not info.get("parent_id")]

        def add_node(sid, depth):
            info = sessions[sid]
            is_current = (sid == current_id)
            alias = info.get("alias", sid)
            msg_count = info.get("messages_count", 0)
            prefix = "    " * depth + ("└── " if depth > 0 else "🌱 ")
            head_tag = " <-- [HEAD]" if is_current else ""
            color = "#a3be8c" if is_current else ("#88c0d0" if depth > 0 else "#81a1c1")

            if alias == sid:
                label_text = f"[{color}]{prefix}{alias} ({msg_count} msgs)[/{color}][#ebcb8b]{head_tag}[/#ebcb8b]"
            else:
                label_text = f"[{color}]{prefix}{alias} [{sid[-6:]}] ({msg_count} msgs)[/{color}][#ebcb8b]{head_tag}[/#ebcb8b]"

            static_node = Static(f"  {label_text}", classes="nav-item", markup=True)
            static_node._original_text = label_text
            session_selector.append(ListItem(static_node, id=f"sess-{sid}"))
            children = [cid for cid, cinfo in sessions.items() if cinfo.get("parent_id") == sid]
            children.sort(key=lambda x: sessions[x].get("updated_at", ""))
            for child in children:
                add_node(child, depth + 1)

        for root in roots:
            add_node(root, 0)

        session_selector.focus()

    async def show_skill_selector(self) -> None:
        """呼出技能选择器层"""
        self.is_selecting = True
        self.marked_skills = set()  # 每次呼出时默认全不选

        chat_zone = self.query_one("#chat-zone")
        skill_selector = self.query_one("#skill-selector")

        chat_zone.add_class("hidden")
        self.query_one("#space-selector").remove_class("active")
        self.query_one("#config-selector").remove_class("active")
        self.query_one("#session-selector").remove_class("active")
        self.query_one("#help-guide").remove_class("active")
        skill_selector.add_class("active")

        await skill_selector.clear()

        # 调用后端的 helper 获取目录
        skills = get_available_skills()
        for skill in skills:
            label_text = f"[ ] {skill}"
            static_node = Static(f"  {label_text}", classes="nav-item", markup=True)
            static_node._original_text = label_text
            static_node._skill_name = skill  # 绑定隐藏数据方便存取
            skill_selector.append(ListItem(static_node, id=f"skill-{skill}"))

        skill_selector.focus()

    async def show_help_guide(self) -> None:
        self.is_selecting = True
        chat_zone = self.query_one("#chat-zone")
        help_guide = self.query_one("#help-guide")

        chat_zone.add_class("hidden")
        self.query_one("#space-selector").remove_class("active")
        self.query_one("#config-selector").remove_class("active")
        self.query_one("#session-selector").remove_class("active")
        self.query_one("#skill-selector").remove_class("active")
        help_guide.add_class("active")

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
            "| `/sessions` | 查看和切换会话分支（Git 风格） |\n"
            "| `/skills` | 浏览并勾选要加载的技能，追加至输入框 |\n"
            "| `/branch <name>` | 从当前会话创建新分支（继承历史） |\n"
            "| `/new <name>` | 创建纯净新分支（仅含 System Prompt） |\n"
            "\n"
            "## 快捷键\n"
            "- `Enter` — 发送消息\n"
            "- `Ctrl+O` — 换行\n"
            "- `Ctrl+Q` — 退出程序\n"
            "- `Escape` — 返回聊天（在 Guide Book 中）\n"
            "\n"
            "## 技能面板快捷键\n"
            "- `1` — 标记（Mark）当前选中的技能\n"
            "- `0` — 取消标记（Unmark）当前选中的技能\n"
            "- `Enter` — 确认并回填到对话框中\n"
            "\n"
            "## 关于\n"
            "PurrCat — 终端里的 AI 聊天猫 🐱"
        )
        help_guide.mount(Markdown(help_text))
        help_guide.scroll_end(animate=False)
        help_guide.focus()

    # ===================== ListView 高亮与选定回调 =====================
    @on(ListView.Highlighted)
    def update_cursor_on_highlight(self, event: ListView.Highlighted):
        for item in event.list_view.query(ListItem):
            try:
                static = item.query_one(Static)
                if hasattr(static, "_original_text"):
                    static.update(f"  {static._original_text}")
            except Exception:
                pass

        if event.item:
            try:
                static = event.item.query_one(Static)
                if hasattr(static, "_original_text"):
                    static.update(f"[bold cyan]>[/bold cyan] {static._original_text}")
            except Exception:
                pass

    @on(ListView.Selected, "#space-selector")
    def switch_space(self, event: ListView.Selected):
        self.current_space = event.item.id
        self.is_selecting = False
        chat_zone = self.query_one("#chat-zone")
        space_selector = self.query_one("#space-selector")

        space_selector.remove_class("active")
        chat_zone.remove_class("hidden")
        self.query_one("#chat-input").focus()

        if self.current_space == "nav-main":
            for child in chat_zone.children:
                if child.id and str(child.id).startswith("task-log-widget"):
                    child.display = False
                else:
                    child.display = True
            chat_zone.scroll_end(animate=False)
        else:
            for child in chat_zone.children:
                if not (child.id and str(child.id).startswith("task-log-widget")):
                    child.display = False
                else:
                    child.display = True
            self._task_switch_pending = True

        self.refresh_chat_state()

    @on(ListView.Selected, "#config-selector")
    def switch_theme(self, event: ListView.Selected):
        selected_id = event.item.id
        color_hex = "#ffffff"
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

        # 动态修改边框颜色（记得把 skill-selector 也加进来）
        zones = ["#top-zone", "#chat-zone", "#space-selector", "#config-selector", "#session-selector",
                 "#skill-selector", "#input-zone"]
        for zone_id in zones:
            try:
                widget = self.query_one(zone_id)
                widget.styles.border = ("round", color_hex)
                widget.styles.border_title_color = color_hex
            except Exception:
                pass

        self.refresh_chat_state()

    @on(ListView.Selected, "#session-selector")
    def switch_session_event(self, event: ListView.Selected):
        target_sid = event.item.id.replace("sess-", "")
        self.is_selecting = False

        chat_zone = self.query_one("#chat-zone")
        session_selector = self.query_one("#session-selector")
        session_selector.remove_class("active")
        chat_zone.remove_class("hidden")
        self.query_one("#chat-input").focus()

        success = checkout_session(target_sid)
        if success:
            for child in chat_zone.query(".msg-space-nav-main"):
                child.remove()

            self.rendered_msg_counts["nav-main"] = 0
            keys_to_delete = [k for k, v in self.tool_widgets.items() if v.has_class("msg-space-nav-main")]
            for k in keys_to_delete:
                del self.tool_widgets[k]

            self.current_space = "nav-main"
            chat_zone.mount(Static(f"🔄 [系统] 已成功检出并恢复会话: {target_sid[-6:]}", classes="help-message"))
            self.refresh_chat_state()

    @on(ListView.Selected, "#skill-selector")
    def submit_skills(self, event: ListView.Selected):
        """确认选择，追加至输入框"""
        self.is_selecting = False
        chat_zone = self.query_one("#chat-zone")
        skill_selector = self.query_one("#skill-selector")

        skill_selector.remove_class("active")
        chat_zone.remove_class("hidden")

        chat_input = self.query_one("#chat-input", ChatInput)
        chat_input.focus()

        # 组装打标记的技能列表并插入到对话框
        if getattr(self, "marked_skills", set()):
            skills_str = ",".join(sorted(list(self.marked_skills)))
            append_text = f"<Fetch Skill First: {skills_str}>"
            current_text = chat_input.text
            if current_text.strip():
                chat_input.insert("\n" + append_text)
            else:
                chat_input.insert(append_text)

            try:
                # 尽力确保光标移动到底部
                chat_input.cursor_position = (chat_input.document.line_count - 1, len(chat_input.document.lines[-1]))
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
        self.query_one("#space-selector").remove_class("active")
        self.query_one("#config-selector").remove_class("active")
        self.query_one("#session-selector").remove_class("active")
        self.query_one("#skill-selector").remove_class("active")
        help_guide.remove_class("active")
        chat_zone.remove_class("hidden")
        self.query_one("#chat-input").focus()

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

            try:
                log_widget = chat_zone.query_one(f"#{widget_id}", Static)
            except Exception:
                needs_update = True

            with task_module.task_set_lock:
                if task_id in task_module.dirty_tasks:
                    needs_update = True
                    task_module.dirty_tasks.remove(task_id)

            if getattr(self, '_task_switch_pending', False):
                needs_update = True
                self._task_switch_pending = False

            if not needs_update:
                return

            log_content = await asyncio.to_thread(format_task_log, task_id)

            if log_widget:
                log_widget.update(log_content)
                log_widget.display = True
            else:
                new_widget = Static(log_content, id=widget_id, markup=True)
                new_widget.styles.padding = (1, 2)
                chat_zone.mount(new_widget)

            chat_zone.scroll_end(animate=False)
            return
        # ================================================================

        history = get_agent_history()
        rendered_count = self.rendered_msg_counts.get(self.current_space, 0)
        visible_history = [msg for msg in history if msg.get("role") != "system"]

        if rendered_count > 0 and len(visible_history) < rendered_count:
            for child in chat_zone.query(f".msg-space-{self.current_space}"):
                child.remove()
            self.tool_widgets.clear()
            self.rendered_msg_counts[self.current_space] = 0
            rendered_count = 0

        if visible_history and rendered_count > 0 and len(visible_history) <= rendered_count:
            last_data = visible_history[-1]
            if last_data.get("role") == "assistant":
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
                                tw.add_class(f"msg-space-{self.current_space}")
                                self.tool_widgets[tc_id] = tw
                                chat_zone.mount(tw)
                                chat_zone.scroll_end(animate=False)

        if len(visible_history) > rendered_count:
            is_initial_load = rendered_count == 0
            for msg in visible_history[rendered_count:]:
                role = msg.get("role")
                content = msg.get("content", "")

                if role == "user":
                    user_messages, system_count = parse_events_content(content)
                    # 渲染用户消息
                    for event_time, event_content in user_messages:
                        if event_time:
                            # 包含时间戳的用户消息
                            new_msg = ChatMessage("user", f"{event_content}", is_new=False)
                        else:
                            new_msg = ChatMessage("user", event_content, is_new=False)
                        new_msg.add_class(f"msg-space-{self.current_space}")
                        chat_zone.mount(new_msg)

                    # 如果有系统消息，显示统计提示
                    # if system_count > 0:
                    #     system_note = Static(f"⚙️ 收到 {system_count} 条系统日志", classes="system-note")
                    #     system_note.add_class(f"msg-space-{self.current_space}")
                    #     chat_zone.mount(system_note)

                elif role == "assistant":
                    is_new_msg = not is_initial_load
                    new_msg = ChatMessage("assistant", content, is_new=is_new_msg)
                    new_msg.add_class(f"msg-space-{self.current_space}")
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
                            tw.add_class(f"msg-space-{self.current_space}")
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
                        print_content = content.replace('[', '\\[').replace(']', '\\]')
                        fallback_msg = f"   └── {print_content}"
                        fb_widget = Static(fallback_msg, classes="tool-result")
                        fb_widget.add_class(f"msg-space-{self.current_space}")
                        chat_zone.mount(fb_widget)

            self.rendered_msg_counts[self.current_space] = len(visible_history)
            chat_zone.scroll_end(animate=False)

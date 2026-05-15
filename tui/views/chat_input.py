from textual.widgets import TextArea, Static
from textual.events import Key
from tui.api import branch_session, new_clean_session, flush_agent_memory


class ChatInput(TextArea):

    def on_mount(self) -> None:
        try:
            self.soft_wrap = True
        except AttributeError:
            pass

    async def on_key(self, event: Key) -> None:
        from tui.views.main_view import MainView

        if event.key == "ctrl+o":
            event.prevent_default()
            self.insert("\n")
        elif event.key == "enter":
            event.prevent_default()
            text = self.text.strip()

            # ==============================
            # 🔴 斜杠指令集中解析与拦截
            # ==============================
            if text == "/sessions":
                await self.app.query_one(MainView).show_session_selector()
                self.clear()

            elif text == "/skills" or text == "/skill":
                await self.app.query_one(MainView).show_skill_selector()
                self.clear()

            elif text.startswith("/branch"):
                branch_name = text[7:].strip()
                main_view = self.app.query_one(MainView)
                chat_zone = main_view.query_one("#chat-zone")

                if branch_name:
                    new_id = branch_session(branch_name)
                    chat_zone.mount(Static(f"🌿 [系统] 已成功拉取并切换到新分支: {branch_name} ({new_id[-6:]})",
                                           classes="help-message"))
                else:
                    chat_zone.mount(
                        Static("❌ [系统] 用法错误: 请提供分支名称，例如 /branch feature_a", classes="help-message"))

                chat_zone.scroll_end(animate=False)
                self.clear()

            elif text.startswith("/new"):
                branch_name = text[4:].strip()
                main_view = self.app.query_one(MainView)
                chat_zone = main_view.query_one("#chat-zone")

                if branch_name:
                    new_id = new_clean_session(branch_name)
                    for child in chat_zone.query(f".msg-space-{main_view.current_space}"):
                        child.remove()

                    keys_to_delete = [k for k, v in main_view.tool_widgets.items() if
                                      v.has_class(f"msg-space-{main_view.current_space}")]
                    for k in keys_to_delete:
                        del main_view.tool_widgets[k]
                    main_view.rendered_msg_counts[main_view.current_space] = 0

                    chat_zone.mount(Static(f"✨ [系统] 已创建并切换到全新纯净分支: {branch_name} ({new_id[-6:]})",
                                           classes="help-message"))
                else:
                    chat_zone.mount(
                        Static("❌ [系统] 用法错误: 请提供分支名称，例如 /new clean_task", classes="help-message"))

                chat_zone.scroll_end(animate=False)
                self.clear()

            elif text == "/switch":
                await self.app.query_one(MainView).show_space_selector()
                self.clear()

            elif text == "/config":
                await self.app.query_one(MainView).show_config_selector()
                self.clear()

            elif text == "/help":
                await self.app.query_one(MainView).show_help_guide()
                self.clear()

            elif text == "/flush":
                main_view = self.app.query_one(MainView)
                chat_zone = main_view.query_one("#chat-zone")

                from textual.widgets import Markdown
                status = Markdown("⏳ 正在压缩主 Agent 记忆，请稍候...", classes="help-message")
                status.add_class(f"msg-space-{main_view.current_space}")
                chat_zone.mount(status)
                chat_zone.scroll_end(animate=False)
                self.clear()

                success = flush_agent_memory()
                if success:
                    status.update("✅ 主 Agent 记忆压缩完成，早期对话已归档。")
                else:
                    status.update("❌ 记忆压缩失败：Agent 未初始化")

            elif text:
                self.app.query_one(MainView).handle_chat_submit(text)
                self.clear()

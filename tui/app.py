from textual.app import App, ComposeResult
from textual.binding import Binding

# 改为引入重构后的 MainView
from .views.chat import MainView

class CatInCupApp(App):
    """Cat-in-Cup - Agentic CLI Edition"""

    CSS_PATH = "styles/main.tcss"
    TITLE = "Cat-in-Cup"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+l", "clear_screen", "Clear", show=False)
    ]

    def compose(self) -> ComposeResult:
        # 直接挂载主视图
        yield MainView(id="main-layout")

    def action_clear_screen(self):
        # 清理当前激活的聊天窗口
        chat_history = self.query_one("#chat-zone")
        for child in chat_history.children:
            child.remove()
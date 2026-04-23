# tui/app.py
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.binding import Binding

from .views.chat import ChatView

class CatInCupApp(App):
    """Cat-in-Cup - Agentic CLI Edition"""

    CSS_PATH = "styles/main.tcss"
    TITLE = "Cat-in-Cup"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+l", "clear_screen", "Clear", show=False)
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="main-content"):
            yield ChatView()

    def action_clear_screen(self):
        chat_history = self.query_one("#chat-history")
        for child in chat_history.children:
            if child.id != "welcome-pet":
                child.remove()
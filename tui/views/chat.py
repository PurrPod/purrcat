from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, TextArea
from textual.widgets import Markdown
from textual.containers import ScrollableContainer

class ChatView(Vertical):
    """Catnip 聊天视图"""
    def compose(self) -> ComposeResult:
        yield Static("Catnip Chat", classes="chat-title")
        with ScrollableContainer(id="chat-messages"):
            yield Markdown("# Welcome to Catnip Chat\n\nStart chatting with your AI assistant!")
        yield TextArea(placeholder="Type your message here...", id="chat-input")

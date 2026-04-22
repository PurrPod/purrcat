from textual.app import ComposeResult
from textual.widgets import Static, Markdown
from textual.containers import Vertical

class Message(Vertical):
    """聊天气泡组件"""
    def __init__(self, sender: str, content: str, is_user: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.sender = sender
        self.content = content
        self.is_user = is_user
    
    def compose(self) -> ComposeResult:
        yield Static(f"{self.sender}:", classes="message-sender")
        yield Markdown(self.content, classes="message-content")

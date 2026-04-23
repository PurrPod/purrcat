from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Input, Markdown
from textual import events

class MessageBlock(Vertical):
    """单条消息气泡"""
    
    def __init__(self, role: str, content: str, **kwargs):
        super().__init__(**kwargs)
        self.role = role
        self.content = content
        # 动态分配 CSS class
        self.add_class(f"-{self.role.lower()}")

    def compose(self) -> ComposeResult:
        display_role = "🐱 Catnip" if self.role == "ai" else "👤 You"
        yield Static(display_role, classes="msg-role")
        yield Markdown(self.content)

class Omnibar(Horizontal):
    """底部的全局输入栏"""
    
    def compose(self) -> ComposeResult:
        yield Static("❯", id="omnibar-prompt")
        yield Input(placeholder="Ask Catnip... (Type '/' for commands)", id="omnibar-input")
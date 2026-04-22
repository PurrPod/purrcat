from textual.app import ComposeResult
from textual.widgets import TextArea, Button
from textual.containers import Horizontal

class Omnibar(Horizontal):
    """聊天输入框组件"""
    def compose(self) -> ComposeResult:
        yield TextArea(placeholder="Type your message here...", id="chat-input")
        yield Button("Send", id="send-button")

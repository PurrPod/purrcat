from textual.app import ComposeResult
from textual.widgets import ListItem, ListView, Static

class Sidebar(ListView):
    """左侧导航栏组件"""
    def compose(self) -> ComposeResult:
        yield ListItem(Static("🐱 Catnip (Chat)"), id="nav-chat")
        yield ListItem(Static("📦 Sandbox"), id="nav-sandbox")
        yield ListItem(Static("📋 Tasks"), id="nav-task")
        yield ListItem(Static("⏰ Schedule"), id="nav-schedule")
        yield ListItem(Static("🔌 Plugins"), id="nav-plugin")
        yield ListItem(Static("⚙️ Settings"), id="nav-setting")

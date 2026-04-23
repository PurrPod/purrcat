from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Input, Switch, Button

class SettingView(Vertical):
    """设置视图"""
    def compose(self) -> ComposeResult:
        yield Static("Settings", classes="section-title")
        with Horizontal():
            yield Static("API Key:", classes="label")
            yield Input(placeholder="API Key", id="api-key")
        with Horizontal():
            yield Static("Enable Plugins:", classes="label")
            yield Switch(id="enable-plugins")
        with Horizontal():
            yield Static("Model Name:", classes="label")
            yield Input(placeholder="Model Name", id="model-name")
        yield Button("Save Settings", id="save-settings")

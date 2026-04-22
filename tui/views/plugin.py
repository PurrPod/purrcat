from textual.app import ComposeResult
from textual.containers import Vertical, Grid
from textual.widgets import Static, Switch

class PluginView(Vertical):
    """插件管理视图"""
    def compose(self) -> ComposeResult:
        yield Static("Plugin Management", classes="section-title")
        with Grid(id="plugin-grid"):
            yield Static("Local Plugins")
            yield Switch(value=True, id="local-plugins")
            yield Static("MCP Plugins")
            yield Switch(value=True, id="mcp-plugins")
            yield Static("Web Plugins")
            yield Switch(value=False, id="web-plugins")

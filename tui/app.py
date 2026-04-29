from textual.app import App
from textual.binding import Binding

from tui.views.chat import MainView, TaskMonitorScreen


class PurrCatTUI(App):
    CSS_PATH = "styles/main.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+t", "open_task_monitor", "Tasks", show=True),
    ]

    def compose(self):
        yield MainView()

    def action_open_task_monitor(self) -> None:
        """Open the task monitor modal"""
        self.push_screen(TaskMonitorScreen())
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static
from textual.screen import ModalScreen
from tui.api import get_task_list, format_task_log


class TaskMonitorScreen(ModalScreen):
    def __init__(self):
        super().__init__()
        self.selected_task = None
        self.showing_log = False

    def compose(self) -> ComposeResult:
        with Vertical(id="task-dialog"):
            yield Static("Task Monitor — PurrCat Background Tasks", id="task-dialog-header")
            yield VerticalScroll(id="task-dialog-list")
            yield Static("Ctrl+q: Close  |  Enter: View Logs  |  Esc: Back", id="task-dialog-footer")

    def on_mount(self):
        self.refresh_task_list()

    def refresh_task_list(self):
        task_list = self.query_one("#task-dialog-list")
        for child in list(task_list.children):
            child.remove()

        tasks = get_task_list()
        if not tasks:
            task_list.mount(Static("No active tasks.", classes="task-detail"))
            return

        for t in tasks:
            state = t.get("state", "unknown")
            state_emoji = {"running": "🟢", "done": "🔵", "error": "🔴", "waiting": "🟡"}.get(state, "⚪")

            name = Static(f"{state_emoji}  {t.get('name', '?')}", classes="task-name")
            state_label = Static(f"State: {state}", classes="task-state " + state)

            expert = t.get("expert_type", "?")
            step = t.get("step", 0)
            tokens = t.get("token_usage", 0)
            created = t.get("create_time", "")
            if isinstance(created, (int, float)):
                import datetime
                created = datetime.datetime.fromtimestamp(created).strftime("%H:%M:%S")

            detail = Static(
                f"  ID: {str(t['id'])[:16]}... | Type: {expert} | Step: {step} | Tokens: {tokens} | {created}",
                classes="task-detail"
            )

            card = Vertical(
                name,
                state_label,
                detail,
                classes="task-card",
                id=f"task-card-{t['id']}"
            )

            task_list.mount(card)

    def view_task_log(self, task_id):
        self.selected_task = task_id
        self.showing_log = True
        task_list = self.query_one("#task-dialog-list")

        for child in list(task_list.children):
            child.remove()

        log_text = format_task_log(task_id)

        log_entries = [
            Static(line, classes="log-entry", markup=True)
            for line in log_text.split("\n")
        ]

        log_viewer = VerticalScroll(*log_entries, id="task-log-viewer")
        task_list.mount(log_viewer)
        log_viewer.focus()

    def key_escape(self):
        if self.showing_log:
            self.showing_log = False
            self.refresh_task_list()
        else:
            self.app.pop_screen()

    def key_enter(self):
        if not self.showing_log:
            cards = list(self.query(".task-card"))
            if cards:
                for c in cards:
                    if c.id and c.id.startswith("task-card-"):
                        task_id = c.id.replace("task-card-", "")
                        self.view_task_log(task_id)
                        break

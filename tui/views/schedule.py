from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, DataTable

class ScheduleView(Vertical):
    """定时调度视图"""
    def compose(self) -> ComposeResult:
        yield Static("Scheduled Tasks", classes="section-title")
        table = DataTable()
        table.add_columns("ID", "Task", "Cron Expression", "Status")
        # 添加一些示例定时任务
        table.add_rows([
            ["1", "Daily Backup", "0 0 * * *", "Active"],
            ["2", "Weekly Report", "0 0 * * 0", "Active"],
            ["3", "Monthly Review", "0 0 1 * *", "Inactive"],
        ])
        yield table

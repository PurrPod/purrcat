from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, DataTable

class TaskView(Vertical):
    """任务管理视图"""
    def compose(self) -> ComposeResult:
        yield Static("Task Management", classes="section-title")
        table = DataTable()
        table.add_columns("ID", "Task", "Status", "Priority")
        # 添加一些示例任务
        table.add_rows([
            ["1", "Implement TUI", "In Progress", "High"],
            ["2", "Fix bug in agent", "Pending", "Medium"],
            ["3", "Add new plugin", "Pending", "Low"],
        ])
        yield table

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, TextArea, Tree

class SandboxView(Horizontal):
    """沙盒视图"""
    def compose(self) -> ComposeResult:
        with Vertical(id="file-tree-container"):
            yield Static("File Tree", classes="section-title")
            tree = Tree("Project")
            # 添加一些示例文件
            tree.root.add_children([
                Tree.Label("src/"),
                Tree.Label("data/"),
                Tree.Label("README.md"),
            ])
            yield tree
        with Vertical(id="code-editor-container"):
            yield Static("Code Editor", classes="section-title")
            yield TextArea("# Sandbox\n\nWrite your code here...", id="code-editor")

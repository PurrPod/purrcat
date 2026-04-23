from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, TextArea, Tree
import os
import time
from textual.reactive import reactive

class SandboxView(Horizontal):
    """沙盒视图 - 跟踪显示 agent_vm 文件夹状态"""
    
    # 响应式状态，用于跟踪文件树是否需要更新
    tree_needs_update = reactive(True)

    def compose(self) -> ComposeResult:
        with Vertical(id="file-tree-container"):
            yield Static("agent_vm File Tree", classes="section-title")
            tree = Tree("agent_vm")
            self._populate_tree(tree)
            # 默认展开根节点
            tree.root.expand()
            yield tree
        with Vertical(id="code-editor-container"):
            yield Static("Code Editor", classes="section-title")
            yield TextArea("# Sandbox\n\nWrite your code here...", id="code-editor")

    def _populate_tree(self, tree):
        """递归填充文件树"""
        try:
            self._add_directory(tree.root, "agent_vm")
        except Exception as e:
            tree.root.add_leaf(f"Error: {e}")

    def _add_directory(self, parent_node, path):
        """递归添加目录和文件"""
        try:
            items = os.listdir(path)
            for item in sorted(items):
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    # 添加目录
                    dir_node = parent_node.add(item)
                    self._add_directory(dir_node, item_path)
                else:
                    # 添加文件
                    parent_node.add_leaf(item)
        except Exception as e:
            parent_node.add_leaf(f"Error: {e}")

    def on_mount(self) -> None:
        """视图挂载时启动定时更新"""
        self.set_interval(5.0, self._update_tree)

    def _update_tree(self) -> None:
        """更新文件树"""
        try:
            # 获取现有的树
            tree = self.query_one(Tree)
            
            # 清空根节点的子节点
            if hasattr(tree.root, 'children'):
                tree.root.children.clear()
            
            # 重新填充树
            self._add_directory(tree.root, "agent_vm")
            
            # 展开根节点
            tree.root.expand()
            
            # 刷新树
            tree.refresh()
        except Exception as e:
            pass
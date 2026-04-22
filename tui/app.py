from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, ListView
from textual.reactive import reactive

# 导入视图组件
from .views.chat import ChatView
from .views.sandbox import SandboxView
from .views.task import TaskView
from .views.schedule import ScheduleView
from .views.plugin import PluginView
from .views.setting import SettingView

# 导入组件
from .components.sidebar import Sidebar

class CatInCupApp(App):
    """Cat-in-Cup 的 Textual TUI 主程序"""
    
    CSS_PATH = "styles/main.tcss" # 绑定你的样式表
    TITLE = "Cat-in-Cup TUI"
    
    # 响应式状态，记录当前激活的视图
    current_view = reactive("nav-chat")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield Sidebar(id="sidebar")
            with Vertical(id="main-content"):
                # 初始内容
                yield ChatView()
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """当用户点击左侧导航时触发"""
        self.current_view = event.item.id

    def watch_current_view(self, old_view: str, new_view: str) -> None:
        """当 current_view 变化时，自动更新右侧的挂载组件"""
        content_container = self.query_one("#main-content")
        # 清除旧内容
        for child in content_container.children:
            child.remove()
        
        # 挂载新内容
        if new_view == "nav-chat":
            content_container.mount(ChatView())
        elif new_view == "nav-sandbox":
            content_container.mount(SandboxView())
        elif new_view == "nav-task":
            content_container.mount(TaskView())
        elif new_view == "nav-schedule":
            content_container.mount(ScheduleView())
        elif new_view == "nav-plugin":
            content_container.mount(PluginView())
        elif new_view == "nav-setting":
            content_container.mount(SettingView())
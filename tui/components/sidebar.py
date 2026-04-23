from textual.app import ComposeResult
from textual.widgets import ListItem, ListView, Static
from textual.containers import Vertical

# 定义小猫的动画帧
CAT_FRAMES = [
    """\
   /\\_/\\
  ( o.o )
   > ^ <
 ╭───────╮
 ╰───────╯
""",
    """\
   /\\_/\\
  ( -.- )
   > ^ <
 ╭───────╮
 ╰───────╯
"""
]

class Sidebar(Vertical):
    """侧边栏组件（包含像素宠物动画和导航）"""
    
    def compose(self) -> ComposeResult:
        # 顶部像素小宠物
        self.pet = Static(CAT_FRAMES[0], classes="pixel-pet-container")
        yield self.pet
        
        # 导航列表
        with ListView(id="nav-list"):
            yield ListItem(Static("🐱 Catnip (Chat)"), id="nav-chat")
            yield ListItem(Static("📦 Sandbox"), id="nav-sandbox")
            yield ListItem(Static("📋 Tasks"), id="nav-task")
            yield ListItem(Static("⏰ Schedule"), id="nav-schedule")
            yield ListItem(Static("🔌 Plugins"), id="nav-plugin")
            yield ListItem(Static("⚙️ Settings"), id="nav-setting")

    def on_mount(self) -> None:
        """组件挂载时启动眨眼动画"""
        self.frame_idx = 0
        # 每隔 3 秒执行一次眨眼逻辑
        self.set_interval(3.0, self.blink)

    def blink(self) -> None:
        """眨眼动作"""
        self.pet.update(CAT_FRAMES[1]) # 闭眼
        # 0.2秒后睁眼
        self.set_timer(0.2, self.open_eyes)

    def open_eyes(self) -> None:
        self.pet.update(CAT_FRAMES[0]) # 睁眼
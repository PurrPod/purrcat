import asyncio
import os
from textual.app import App
from textual.binding import Binding

# 引入基础配置和工具初始化
from src.utils.config import initialize_config
from src.plugins.route.base_tool import init_tool, init_mcp_tools
from src.sensor.system.const import start_sensors

# 引入 agent 模块核心
from src.agent.manager import init_agent, get_agent, shutdown_agent
from src.sensor.message.feishu import start_lark_sensor
from tui.views.chat import MainView, TaskMonitorScreen


class PurrCatTUI(App):
    CSS_PATH = "styles/main.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+t", "open_task_monitor", "Tasks", show=True),
    ]

    def compose(self):
        yield MainView()

    async def on_mount(self) -> None:
        """复刻 backend.py 的 lifespan 初始化逻辑"""

        # 1. 代理清理（按需保留）
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)

        # 2. 初始化配置文件与全局工具注册表
        initialize_config()
        init_tool()
        # 检查 tool.jsonl 里有没有 MCP 条目，没有才连一次注册（秒过）
        await init_mcp_tools()
        start_sensors()

        # 3. 实例化 Agent 并加载历史记忆
        self.agent = init_agent()

        # 4. 启动其他传感器（如飞书）
        start_lark_sensor(get_agent())

    def action_open_task_monitor(self) -> None:
        """Open the task monitor modal"""
        self.push_screen(TaskMonitorScreen())

    async def on_unmount(self) -> None:
        """复刻 backend.py 的 teardown 销毁逻辑，确保优雅退出"""
        self.notify("正在安全关闭系统，请稍候...", severity="warning")
        # Manager 内部有 3秒/10秒 的 join 等待，并会执行最后一次 save_checkpoint
        await asyncio.to_thread(shutdown_agent)


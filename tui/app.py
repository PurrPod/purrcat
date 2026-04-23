import asyncio
import os
from textual.app import App
from textual.binding import Binding

# 引入基础配置和工具初始化
from src.utils.config import initialize_config
from src.plugins.route.base_tool import _init_tool_async, init_tool
from src.sensor.const import start_sensors

# 引入 agent 模块核心
from src.agent import agent as agent_module
from src.sensor.feishu import start_lark_sensor

# 引入你的主视图
from tui.views.chat import MainView

# 全局暴露给 tui/api.py 调用（如同 backend.py 中的 global agent）
global_agent = None


class CatInCupTUI(App):
    CSS_PATH = "styles/main.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def compose(self):
        yield MainView()

    async def on_mount(self) -> None:
        """复刻 backend.py 的 lifespan 初始化逻辑"""
        global global_agent

        # 1. 代理清理（按需保留）
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)

        # 2. 初始化配置文件与全局工具注册表
        initialize_config()
        init_tool()
        _init_tool_async()
        start_sensors()

        # 3. 实例化 Agent 并加载历史记忆
        self.agent = agent_module.Agent.load_checkpoint()
        global_agent = self.agent  # 挂载到全局，供 api.py 读取

        # 4. 启动 Agent 的核心处理引擎 (sensor)
        self.agent_sensor_task = asyncio.create_task(asyncio.to_thread(self.agent.sensor))

        # 5. 启动其他传感器（如飞书）
        start_lark_sensor(self.agent)

    async def on_unmount(self) -> None:
        """复刻 backend.py 的 teardown 销毁逻辑，确保优雅退出"""
        self.notify("正在关闭系统...", severity="warning")

        try:
            if hasattr(self, "agent"):
                self.agent.stop()
        except Exception:
            pass

        try:
            if hasattr(self, "agent_sensor_task"):
                await asyncio.wait_for(self.agent_sensor_task, timeout=2)
        except Exception:
            try:
                self.agent_sensor_task.cancel()
            except Exception:
                pass


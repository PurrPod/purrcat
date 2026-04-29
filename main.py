import asyncio
import os
import warnings
import argparse

warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine 'ExpiringCache._start_clear_cron' was never awaited")
warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated as an API")

from src.utils.config import initialize_config
from src.plugins.route.base_tool import init_tool, start_mcp_background_init
from src.sensor.system.const import start_sensors
from src.agent.manager import init_agent, get_agent, shutdown_agent
from src.sensor.message.feishu import start_lark_sensor


async def init_core():
    """初始化核心后台服务"""
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)

    initialize_config()
    init_tool()
    start_mcp_background_init()
    start_sensors()

    agent = init_agent()
    start_lark_sensor(agent)
    print("后台服务与传感器已启动完毕。")


async def shutdown_core():
    """清理并关闭核心后台服务"""
    print("正在安全关闭系统，请稍候...")
    await asyncio.to_thread(shutdown_agent)


async def main_async(enable_tui: bool):
    await init_core()

    try:
        if enable_tui:
            from tui.app import PurrCatTUI
            app = PurrCatTUI()
            await app.run_async()
        else:
            print("以无界面(Headless)模式运行中，按 Ctrl+C 退出...")
            await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await shutdown_core()


def main():
    parser = argparse.ArgumentParser(description="PurrCat Agent 启动脚本")
    parser.add_argument("--headless", action="store_true", help="不启动 TUI，仅在后台运行")
    args = parser.parse_args()

    asyncio.run(main_async(enable_tui=not args.headless))


if __name__ == "__main__":
    main()
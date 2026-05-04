import asyncio
import os
import warnings
import argparse
import threading

warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine 'ExpiringCache._start_clear_cron' was never awaited")
warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated as an API")

from src.tool.callmcp.callmcp import initialize_mcp
from src.agent.manager import init_agent, get_agent, shutdown_agent
from src.sensor import auto_discover_and_start
from src.memory.purrmemo import get_memory_client


async def init_core():
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)

    initialize_mcp()

    agent = init_agent()
    auto_discover_and_start()
    get_memory_client()

    print("[+] Backend services and sensors started")


async def shutdown_core():
    print("[*] Shutting down system safely...")
    await asyncio.to_thread(shutdown_agent)


async def run_tui():
    from tui.app import PurrCatTUI
    app = PurrCatTUI()
    await app.run_async()


async def main_async(enable_tui: bool):
    await init_core()

    if enable_tui:
        print("[*] Starting TUI...")
        try:
            await run_tui()
        except Exception as e:
            print(f"[-] TUI error: {e}")
            print("[*] Falling back to headless mode...")
            enable_tui = False

    if not enable_tui:
        print("[*] Running in headless mode, press Ctrl+C to exit...")
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await shutdown_core()


def main():
    parser = argparse.ArgumentParser(description="PurrCat Agent")
    parser.add_argument("--headless", action="store_true", help="Run without TUI")
    args = parser.parse_args()

    asyncio.run(main_async(enable_tui=not args.headless))


if __name__ == "__main__":
    main()
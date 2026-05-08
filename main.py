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


async def init_core(cli_session_id: str = None, cli_branch_name: str = None):
    # 注意：如果你的大模型 API 需要通过代理访问（如国内访问 OpenAI/Claude），请取消下面两行注释
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)

    initialize_mcp()
    agent = init_agent(session_id=cli_session_id)

    def bg_init_services():
        try:
            auto_discover_and_start()
        except Exception as e:
            print(f"⚠️ [Background] Sensor 启动异常: {e}")
        try:
            get_memory_client()
        except Exception as e:
            print(f"⚠️ [Background] Memory client 启动异常: {e}")

    threading.Thread(target=bg_init_services, daemon=True, name="BgServicesThread").start()

    if cli_branch_name:
        from src.agent.manager import manager
        new_id = manager.branch_current_session(cli_branch_name)
        print(f"🌿 [CLI] 已从 {cli_session_id or '最新会话'} 创建并切换到新分支: {cli_branch_name} ({new_id})")

    print("[+] Backend services and sensors started")


async def shutdown_core():
    print("[*] Shutting down system safely...")
    await asyncio.to_thread(shutdown_agent)


async def run_tui():
    from tui.app import PurrCatTUI
    app = PurrCatTUI()
    await app.run_async()


async def main_async(enable_tui: bool, cli_session: str = None, cli_branch: str = None):
    await init_core(cli_session_id=cli_session, cli_branch_name=cli_branch)

    try:
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
            await asyncio.Event().wait()
            
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[*] 检测到中断信号，准备退出...")
    finally:
        # 确保无论什么分支，最后都会安全关停 Agent 和后台线程
        await shutdown_core()


def main():
    parser = argparse.ArgumentParser(description="PurrCat Agent")
    parser.add_argument("--headless", action="store_true", help="Run without TUI")
    parser.add_argument("--session", type=str, help="Specify session ID to load")
    parser.add_argument("--branch", type=str, help="Create new branch with given name on startup")
    args = parser.parse_args()

    asyncio.run(main_async(enable_tui=not args.headless, cli_session=args.session, cli_branch=args.branch))


if __name__ == "__main__":
    main()
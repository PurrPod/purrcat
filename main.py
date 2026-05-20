import asyncio
import os
import warnings
import argparse
import threading

# 仅在头部保留极轻量级且必须立即启动的核心 Agent 模块
from src.agent import init_agent, shutdown_agent, branch_session


def _setup_warnings():
    warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine 'ExpiringCache._start_clear_cron' was never awaited")
    warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated as an API")


def _bg_heavy_init():
    """所有重型模块的后台初始化和预热（彻底剥离主线程）"""
    print("[Background] 开始后台预热重型服务...")
    
    # 1. 初始化并拉取 MCP Schema
    try:
        from src.tool.callmcp.callmcp import initialize_mcp
        initialize_mcp()
    except Exception as e:
        print(f"⚠️ [Background] MCP 初始化异常: {e}")

    # 2. 扫描并启动所有传感器插件
    try:
        from src.sensor import auto_discover_and_start
        auto_discover_and_start()
    except Exception as e:
        print(f"⚠️ [Background] Sensor 启动异常: {e}")

    # 3. 初始化并预热记忆库与 Embedding 引擎
    try:
        from src.memory import init_memory
        init_memory()

        # [消除冷启动惩罚] 触发一次单例的 __new__，提前把重型本地模型加载到内存
        from src.tool.search.semantic_utils import LocalEmbeddingSearcher
        LocalEmbeddingSearcher()

        from src.tool.search.skill_search import SkillSearcher
        SkillSearcher()
        
        print("✅ [Background] 本地 Embedding 模型与检索库预热就绪")
    except Exception as e:
        print(f"⚠️ [Background] 记忆库/模型预热异常: {e}")

    # 4. 加载历史任务 (磁盘 I/O 操作)
    try:
        from src.harness.process import auto_load_all_tasks
        auto_load_all_tasks()
        print("✅ [Background] 历史任务工作流加载就绪")
    except Exception as e:
        print(f"⚠️ [Background] 历史任务加载异常: {e}")


async def init_core(cli_session_id: str = None, cli_branch_name: str = None):
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)

    # 1. 核心 Agent 在主线程立即启动，保证 TUI 和 API 秒开
    init_agent(session_id=cli_session_id)

    if cli_branch_name:
        new_id = branch_session(cli_branch_name)
        print(f"🌿 [CLI] 已从 {cli_session_id or '最新会话'} 创建并切换到新分支: {cli_branch_name} ({new_id})")

    # 2. 启动后台初始化线程，将耗时操作完全剥离
    threading.Thread(target=_bg_heavy_init, daemon=True, name="BgHeavyInitThread").start()

    print("[+] Agent core initialized, heavy services warming up in background...")


async def shutdown_core():
    print("[*] Shutting down system safely...")
    await asyncio.to_thread(shutdown_agent)


async def run_tui():
    from tui.app import PurrCatTUI
    app = PurrCatTUI()
    await app.run_async()


async def run_api(host: str = "0.0.0.0", port: int = 8000):
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    import logging
    
    # API 路由也尽量懒加载，防止影响入口速度
    from server.api.chat import router as chat_router
    from server.api.graph import router as graph_router
    from server.api.task import router as task_router
    from server.api.config import router as config_router
    from server.api.memory import router as memory_router
    from server.api.tools import router as tools_router

    app = FastAPI(title="PurrCat API System")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat_router)
    app.include_router(graph_router)
    app.include_router(task_router)
    app.include_router(config_router)
    app.include_router(memory_router)
    app.include_router(tools_router)

    @app.get("/")
    def ping():
        return {"message": "Meow! PurrCat Backend is running."}

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


async def main_async(enable_tui: bool, enable_api: bool, api_port: int, cli_session: str = None, cli_branch: str = None):
    # 核心极速启动
    await init_core(cli_session_id=cli_session, cli_branch_name=cli_branch)

    api_task = None
    tui_task = None

    try:
        if enable_api:
            print(f"[*] Starting API server on http://0.0.0.0:{api_port}...")
            api_task = asyncio.create_task(run_api(port=api_port))

        if enable_tui:
            print("[*] Starting TUI...")
            try:
                tui_task = asyncio.create_task(run_tui())
                await tui_task
            except Exception as e:
                print(f"[-] TUI error: {e}")
                print("[*] Falling back to headless mode...")
                enable_tui = False

        if not enable_tui:
            print("[*] Running in headless mode, press Ctrl+C to exit...")
            if api_task:
                await api_task
            else:
                await asyncio.Event().wait()
            
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[*] 检测到中断信号，准备退出...")
    finally:
        if api_task and not api_task.done():
            api_task.cancel()
            try:
                await asyncio.wait_for(api_task, timeout=2.0)
            except BaseException:
                pass

        try:
            await shutdown_core()
        except BaseException:
            pass


def main():
    _setup_warnings()
    parser = argparse.ArgumentParser(description="PurrCat Agent")
    parser.add_argument("--headless", action="store_true", help="Run without TUI")
    parser.add_argument("--session", type=str, help="Specify session ID to load")
    parser.add_argument("--branch", type=str, help="Create new branch with given name on startup")
    parser.add_argument("--api", action="store_true", help="Enable API server")
    parser.add_argument("--api-port", type=int, default=8000, help="API server port (default: 8000)")
    args = parser.parse_args()

    try:
        asyncio.run(main_async(
            enable_tui=not args.headless,
            enable_api=args.api,
            api_port=args.api_port,
            cli_session=args.session,
            cli_branch=args.branch
        ))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
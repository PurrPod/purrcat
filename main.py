import asyncio
import os
import warnings
import argparse

# 核心模块
from src.agent import init_agent, shutdown_agent, branch_session
from src.tool.callmcp.session_manager import mcp_manager

# 定义一个全局事件，防止 API 和 LLM 在未初始化完之前偷跑
SYSTEM_READY_EVENT = asyncio.Event()


def _setup_warnings():
    warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine 'ExpiringCache._start_clear_cron' was never awaited")
    warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated as an API")


async def _bg_heavy_init(enable_tui: bool):
    """🌟 终极重构：打散耗时任务，按优先级延迟加载，保证秒级首屏"""

    # 1. 强制休眠 0.5 秒，让 FastAPI 的 uvicorn 和 Textual 界面先完成绑定和渲染
    await asyncio.sleep(0.5)
    if not enable_tui:
        print("[Background] API/UI已就绪，开始后台预热服务...")

    # 2. 轻量级加载：读取 MCP 和 Skill 的元数据（不计算向量）
    def _init_light_tools():
        from src.tool.callmcp.callmcp import initialize_mcp_sync
        from src.tool.search.mcp_search import MCPSearcher
        from src.tool.search.skill_search import SkillSearcher

        initialize_mcp_sync()
        MCPSearcher()  # 触发 __init__ 读取 JSON
        SkillSearcher()  # 触发 __init__ 读取 MD

    await asyncio.to_thread(_init_light_tools)

    # 3. 释放一下事件循环，防卡顿
    await asyncio.sleep(0.1)

    # 4. 启动传感器 (由于已经将下载改为了后台线程，这里不会阻塞)
    def _start_sensors():
        from src.sensor import auto_discover_and_start

        auto_discover_and_start()

    await asyncio.to_thread(_start_sensors)

    await asyncio.sleep(0.1)

    # 5. 后台慢速加载：计算向量和加载大模型
    def _build_heavy_vectors():
        from src.tool.search.mcp_search import MCPSearcher
        from src.tool.search.skill_search import SkillSearcher

        MCPSearcher().build_vectors_in_background()
        SkillSearcher().build_vectors_in_background()

    # 用独立的 Task 去算矩阵，完全不影响主体
    asyncio.create_task(asyncio.to_thread(_build_heavy_vectors))

    # 6. 后台会话对账 (取代原本开局的耗时操作)
    def _reconcile_sessions():
        from src.agent.session_store import SessionStore
        from src.harness.process import auto_load_all_tasks

        SessionStore.background_sync_sessions()
        auto_load_all_tasks()

    asyncio.create_task(asyncio.to_thread(_reconcile_sessions))

    SYSTEM_READY_EVENT.set()
    if not enable_tui:
        print("✅ [Background] 所有后台子系统派发完毕！")


async def init_core(cli_session_id: str = None, cli_branch_name: str = None, enable_tui: bool = False):
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)

    # 1. 核心 Agent 在主线程立即启动，保证 TUI 和 API 秒开
    init_agent(session_id=cli_session_id)

    if cli_branch_name:
        new_id = branch_session(cli_branch_name)
        if not enable_tui:
            print(f"🌿 [CLI] 已从 {cli_session_id or '最新会话'} 创建并切换到新分支: {cli_branch_name} ({new_id})")

    # 2. 启动后台异步预热，使用 asyncio.create_task 替代 threading.Thread
    asyncio.create_task(_bg_heavy_init(enable_tui))

    if not enable_tui:
        print("[+] Agent core initialized, heavy services warming up in background...")


async def shutdown_core():
    # 强制清理遗留的 MCP Server 子进程
    try:
        await mcp_manager.shutdown_all()
    except Exception:
        pass
    await asyncio.to_thread(shutdown_agent)


async def run_api(host: str = "0.0.0.0", port: int = 8000):
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    import logging
    
    # API 路由也尽量懒加载，防止影响入口速度
    from src.server.api.chat import router as chat_router
    from src.server.api.graph import router as graph_router
    from src.server.api.task import router as task_router
    from src.server.api.config import router as config_router
    from src.server.api.memory import router as memory_router
    from src.server.api.tools import router as tools_router
    from src.server.api.system import router as system_router
    from src.server.api.request import router as request_router
    from src.server.api.filesystem import router as filesystem_router

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
    app.include_router(system_router)
    app.include_router(request_router)
    app.include_router(filesystem_router)

    @app.get("/")
    def ping():
        return {"message": "Meow! PurrCat Backend is running."}

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    # 🌟 关键修复：关闭 Uvicorn 的信号处理，避免与 Textual 抢夺 Ctrl+C 导致死锁
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    # 取消 uvicorn 的 signal handler 注册
    server.install_signal_handlers = lambda: None
    
    try:
        await server.serve()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


async def main_async(enable_tui: bool, enable_api: bool, api_port: int, cli_session: str = None, cli_branch: str = None):
    # 启动核心
    await init_core(cli_session, cli_branch, enable_tui)

    tasks = []
    if enable_api:
        if not enable_tui:
            print(f"[*] API server: http://0.0.0.0:{api_port}")
        api_task = asyncio.create_task(run_api(port=api_port))
        tasks.append(api_task)

    if enable_tui:
        from tui.app import PurrCatTUI
        app = PurrCatTUI()
        tui_task = asyncio.create_task(app.run_async())
        tasks.append(tui_task)

    try:
        if tasks:
            # 使用 FIRST_COMPLETED，这样无论 TUI 退出还是 API 崩溃，都能正常结束
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        else:
            print("[*] Headless 模式运行中, 按 Ctrl+C 退出...")
            await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        # 清理所有任务
        for t in tasks:
            if not t.done():
                t.cancel()
        await shutdown_core()


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
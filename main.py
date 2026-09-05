import asyncio
import multiprocessing
import os
import sys
import warnings
import argparse

# Windows 下管道 stdout/stderr 默认 GBK 编码，print 含 emoji 会抛
# UnicodeEncodeError 直接崩掉整个后端进程（Electron 用管道拉起时必现）。
# 必须在导入任何业务模块之前重配为 UTF-8 + errors=replace，杜绝崩溃。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 🌟 配置初始化必须在所有业务模块 import 之前执行：
# import 链上存在模块级副作用（如 usage_tracer 实例化时会创建 ~/.purrcat 子目录），
# 若目录先被创建，"目录存在即跳过"的判断会让模板配置永远不生成（首启配置为空的根因）
from src.utils.initial import ensure_initialized

ensure_initialized()

# 🌟 静态资源 MIME 修正：Python 的 mimetypes 在 Windows 上读注册表猜类型，
# 普通用户机器上 .js 常被注册为 text/plain（Windows 默认值），Starlette 便会以
# text/plain 返回前端 JS 包 → Chromium 拒绝执行模块脚本 → 首屏白屏（只剩 CSS
# 渲染的顶部网点条）。开发者机器因装过开发工具注册表正确，故无法本地复现。
# 必须在 StaticFiles 挂载（guess_type 调用）前强制覆盖。
import mimetypes as _mimetypes

_mimetypes.add_type("text/javascript", ".js")
_mimetypes.add_type("text/javascript", ".mjs")
_mimetypes.add_type("text/css", ".css")


def _setup_file_logging():
    """🌟 stdout/stderr 同步落盘到 ~/.purrcat/logs/backend.log。
    生产模式后端由 Electron 管道拉起，用户看不到控制台；后端崩溃时报错
    只打在无人可见的管道里（表现为白屏，无从排查）。落盘后让用户把日志
    发回来即可定位。注意：若连日志文件都没生成，说明解释器本身没起来
    （DLL 缺失/杀软拦截），这本身就是强信号。
    """
    try:
        import datetime as _dt

        from src.utils.initial import PURRCAT_DIR

        class _Tee:
            def __init__(self, stream, fobj):
                self._stream, self._f = stream, fobj

            def write(self, s):
                try:
                    self._stream.write(s)
                except Exception:
                    pass
                try:
                    self._f.write(s)
                except Exception:
                    pass

            def flush(self):
                for target in (self._stream, self._f):
                    try:
                        target.flush()
                    except Exception:
                        pass

            # 🌟 uvicorn 的 logging formatter 会调用 sys.stdout.isatty()，
            # 其他库也可能访问 fileno()/encoding/writelines 等——未实现的属性
            # 一律透传给原始流，避免 "no attribute" 崩溃。
            # 下划线守卫：防止 _stream 尚未赋值时（copy/pickle 等）无限递归
            def isatty(self):
                return False

            def __getattr__(self, name):
                if name.startswith("_"):
                    raise AttributeError(name)
                return getattr(self._stream, name)

        log_dir = os.path.join(PURRCAT_DIR, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "backend.log")
        # 超过 5MB 轮转，防止无限增长
        try:
            if os.path.exists(log_path) and os.path.getsize(log_path) > 5 * 1024 * 1024:
                os.replace(log_path, log_path + ".old")
        except Exception:
            pass
        # buffering=1 行缓冲：进程被强杀（taskkill /F）时也不丢最后的崩溃日志
        _f = open(log_path, "a", encoding="utf-8", errors="replace", buffering=1)
        sys.stdout = _Tee(sys.stdout, _f)
        sys.stderr = _Tee(sys.stderr, _f)
        print(
            f"=== PurrCat backend start {_dt.datetime.now():%Y-%m-%d %H:%M:%S} "
            f"pid={os.getpid()} log={log_path} ==="
        )
    except Exception:
        pass  # 日志系统绝不能阻断主流程


_setup_file_logging()

# 核心模块
from src.agent import init_agent, shutdown_agent, branch_session
from src.tool.callmcp.session_manager import mcp_manager

# 定义一个全局事件，防止 API 和 LLM 在未初始化完之前偷跑
SYSTEM_READY_EVENT = asyncio.Event()


def _setup_warnings():
    warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine 'ExpiringCache._start_clear_cron' was never awaited")
    warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated as an API")
    # 🌟 在程序启动时就拦截 PyTorch 的 pin_memory 警告（必须在 sentence_transformers 导入前生效）
    warnings.filterwarnings("ignore", message=".*'pin_memory' argument is set as true but no accelerator is found.*", category=UserWarning)


async def _bg_heavy_init(enable_tui: bool):
    """🌟 终极重构：打散耗时任务，按优先级延迟加载，保证秒级首屏"""

    # 1. 强制休眠 0.5 秒，让 FastAPI 的 uvicorn 和 Textual 界面先完成绑定和渲染
    await asyncio.sleep(0.5)
    if not enable_tui:
        print("[*] API/UI已就绪，开始后台预热服务...")

    # 2. 嵌入模型 & 沙盒镜像 & MCP/Skill 元数据（不阻塞前台）
    def _init_light_tools():
        from src.tool.callmcp.callmcp import initialize_mcp_sync
        from src.tool.search.mcp_search import MCPSearcher
        from src.tool.search.skill_search import SkillSearcher
        from src.utils.embedding_setup import ensure_embedding_model
        from src.utils.sandbox_setup import ensure_sandbox_image

        initialize_mcp_sync()
        MCPSearcher()  # 触发 __init__ 读取 JSON
        SkillSearcher()  # 触发 __init__ 读取 MD
        ensure_embedding_model()   # 缺则后台线程下载（~120MB）
        ensure_sandbox_image()     # 缺则后台线程拉取 light 镜像

    await asyncio.to_thread(_init_light_tools)

    # 🌟 依赖就绪检查：git/uv/node/嵌入模型/沙盒，缺则向 requests.json 推送 pending 警告
    # 放在 _init_light_tools 之后：此时自动下载/拉取线程已派发，检查结果反映最新状态
    try:
        from src.utils.dependency_check import check_and_warn_dependencies
        check_and_warn_dependencies()
    except Exception as e:
        print(f"[!] 启动依赖检查失败: {e}")

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
        print("[*] 所有后台子系统派发完毕！")


async def init_core(cli_session_id: str = None, cli_branch_name: str = None, enable_tui: bool = False):
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)

    # 1. 核心 Agent 在主线程立即启动，保证 TUI 和 API 秒开
    init_agent(session_id=cli_session_id)

    if cli_branch_name:
        new_id = branch_session(cli_branch_name)
        if not enable_tui:
            print(f"[*] 已从 {cli_session_id or '最新会话'} 创建并切换到新分支: {cli_branch_name} ({new_id})")

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
    from src.server.api.evolve import router as evolve_router
    from src.server.api.terminal import router as terminal_router
    from src.server.api.paradigms import router as paradigms_router

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
    app.include_router(evolve_router)
    app.include_router(terminal_router)
    app.include_router(paradigms_router)

    # 🌟 健康检查必须注册在 app.mount("/") 之前！
    # Starlette 按注册顺序匹配路由，"/" 的静态文件挂载是贪婪前缀匹配，
    # 会吞掉它之后注册的所有路由（/api/health 会变成 404），
    # 导致 Electron 的生产模式轮询永远失败、白屏等 60 秒。
    @app.get("/api/health")
    def ping():
        return {"message": "PurrCat Backend is running."}

    # 🌟 托管前端构建产物（打包成桌面应用后，前后端同源单端口运行）。
    # 静态文件挂载放到所有 API 路由最后，避免遮蔽 /api/* 接口。
    from fastapi.staticfiles import StaticFiles
    from pathlib import Path as _Path
    _ui_dist = _Path(__file__).resolve().parent / "ui" / "dist"
    if _ui_dist.exists():
        app.mount("/", StaticFiles(directory=str(_ui_dist), html=True), name="ui")

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
    # 🌟 PyInstaller 打包后 Windows spawn 子进程必需：检测到自己是 spawn 的子进程时
    # 直接执行 multiprocessing 引导协议，而不是重新跑一遍主程序入口（否则会再起一个服务端）
    multiprocessing.freeze_support()

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
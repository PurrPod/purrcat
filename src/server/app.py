"""FastAPI application factory shared by the runtime entry point and docs tooling.

``create_app`` only assembles routes, middleware and lifecycle hooks. It never
binds a socket, starts a thread or writes runtime state, so generators and tests
can import the exact production route table without booting the service.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api_port import clear_runtime_state, write_runtime_state

_WEBMIN_ROOT = Path(__file__).resolve().parents[2] / "ui" / "web-minimal"


def create_app(port: int | None = None) -> FastAPI:
    """Build the API app.

    ``port`` publishes the actual listening port while the server runs. Pass
    ``None`` for offline consumers (OpenAPI generation, tests) to skip that
    state publication entirely.
    """

    # Routers are imported lazily to keep entry-point startup fast.
    from src.server.api.acp import router as acp_router
    from src.server.api.chat import router as chat_router
    from src.server.api.config import router as config_router
    from src.server.api.evolve import router as evolve_router
    from src.server.api.filesystem import router as filesystem_router
    from src.server.api.graph import router as graph_router
    from src.server.api.memory import router as memory_router
    from src.server.api.paradigms import router as paradigms_router
    from src.server.api.projects import router as projects_router
    from src.server.api.request import router as request_router
    from src.server.api.system import router as system_router
    from src.server.api.task import router as task_router
    from src.server.api.terminal import router as terminal_router
    from src.server.api.tools import router as tools_router
    from src.server.api.webmin import router as webmin_router

    app = FastAPI(title="PurrCat API System")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat_router)
    app.include_router(projects_router)
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
    app.include_router(acp_router)
    app.include_router(webmin_router)

    # 🌟 关闭时回收所有插件后端子进程，避免残留孤儿进程
    from src.server.api import plugin_runtime as _plugin_runtime

    @app.on_event("shutdown")
    def _shutdown_plugin_runtimes():
        _plugin_runtime.stop_all()

    if port is not None:
        # 🌟 实际端口落盘：外部消费者（ACP relay / 配置中心）读它来发现本次运行的真实端口。
        # 写在 startup：uvicorn 此时已完成 bind，绑定失败的进程不会留下误导性的状态文件。
        @app.on_event("startup")
        def _publish_runtime_port():
            write_runtime_state(port)

        @app.on_event("shutdown")
        def _clear_runtime_port():
            clear_runtime_state()

    # 🌟 健康检查必须注册在静态挂载之前！
    # Starlette 按注册顺序匹配路由，静态文件挂载是贪婪前缀匹配，
    # 会吞掉它之后注册的所有路由（/api/health 会变成 404）。
    @app.get("/api/health")
    def ping():
        return {"message": "PurrCat Backend is running."}

    # 静态文件挂载放到所有 API 路由最后，避免遮蔽 /api/* 接口。
    if _WEBMIN_ROOT.exists():
        app.mount(
            "/minimal",
            StaticFiles(directory=str(_WEBMIN_ROOT), html=True),
            name="webmin",
        )

    # 🌟 极简模式静态资源禁用缓存：host.js / theme.css / 插件 JS 等改动后，
    # 仅刷新页面即可生效，避免 Electron 渲染进程命中旧缓存导致"改了没反应"。
    @app.middleware("http")
    async def _webmin_no_cache(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/minimal") or path.startswith("/api/webmin"):
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            response.headers["Pragma"] = "no-cache"
        return response

    return app

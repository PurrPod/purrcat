# 开发指南

按前端 / 后端 / 桌面壳拆分。接口见 [API 参考](../api/README.md)，扩展点见 [插件开发](../plugins/README.md)。

## 技术栈

- 后端：Python 3.10+、FastAPI、uvicorn、Docker SDK、ONNX；ChromaDB + BM25/jieba。
- 前端：TypeScript + esbuild，无框架；极简宿主 + iframe 插件。
- 桌面：Electron 31（`contextIsolation: true`）、electron-builder、NSIS。
- 工具链：uv、npm、PyInstaller。

## 目录地图

| 路径 | 作用 |
| --- | --- |
| `main.py` | 后端入口：初始化配置 → Agent → FastAPI |
| `src/agent/` | 主循环、会话存储、范式 Hook、子代理、心跳 |
| `src/model/` | 模型门面、Key 分配、并发、用量追踪 |
| `src/tool/` | Bash / FileSystem / BrainStorm / Task / Search / Fetch / Memo / Request / Cron / CallMCP / KernelUpgrade |
| `src/harness/` | DAG 引擎与节点扩展 |
| `src/memory/` | PurrMemo（`purrmemo/core/storage/*_engine.py`） |
| `src/sensor/` + `src/server/acp/` | Sensor 生命周期、ACP 协议 |
| `src/server/api/` | 全部 HTTP/WS 路由与插件运行时 |
| `src/evolve/` | 进化工厂（skill/mcp/sensor/agentloop/graph/ui_plugin） |
| `ui/web-minimal/` | 极简 UI：宿主 TS 源码 + 内置插件 |
| `electron/` | 桌面主进程、preload、端口分配 |
| `installer/` | 独立安装器（另一个 Electron 应用） |
| `scripts/` | 开发启动、vendor 同步、API 文档校验、ACP 转接 |
| `docs/` | 接口、插件与开发文档 |

## 运行拓扑

```text
Electron 主进程 (electron/main.js)
├─ 单实例锁 · GPU 降级 · 9222 CDP · 控制口 ~/.purrcat/run/control.json
├─ BrowserWindow → http://127.0.0.1:<apiPort>/minimal/  (preload 暴露 window.purrcat)
├─ WebContentsView 多标签内置浏览器（原生层，永远盖住 DOM）
└─ Python 后端 sidecar（dev: uv run main.py / prod: resources/backend/main.exe）
     └─ FastAPI: /api/* · /acp/* · /minimal · 插件静态与 RPC · WebSocket
```

主进程只做壳与系统能力，业务状态与数据全在 Python 后端，前端通过同源 `/api/*` 取数。

## 环境准备

```powershell
npm install          # 自动执行 postinstall → sync-vendor
uv sync              # Python 依赖
```

Node 需满足 `>=18 <24`（见 `package.json` 的 `engines`）。

## 开发启动

```powershell
npm run dev          # predev 自动 sync-vendor + build:ui → 选端口 → 后端 → Electron
npm run dev:split    # 跳过宿主预构建（仅同步 vendor），要求产物已是最新
```

`scripts/dev.mjs`：选可用端口 → 起后端 → 探测端口就绪 → 起 Electron（`ELECTRON_DEV=1`）→ 任一进程退出即整体清理。

## 常用命令

```powershell
npm run build:ui     # esbuild 打包宿主 → ui/web-minimal/assets/host.js(+map)
npm run watch:ui     # 增量重建，长时间改宿主时用
npm run typecheck    # tsc --noEmit，strict 全开
npm run dist         # electron-builder 打包桌面安装包
npm run installer:dev# 以开发模式启动独立安装器
uv run python main.py --api --headless --api-port 8000   # 只起后端
```

提交前按需执行：

```powershell
ruff check src/ scripts/
ruff format --check src/ scripts/
python scripts/check_api_docs.py      # 改了 src/server 必跑
node --check electron/main.js
npm run typecheck && npm run build:ui
python -m pytest tests/test_api_port.py
```

## 分册

- [后端开发](backend.md)
- [前端开发](frontend.md)
- [桌面壳与安装器](installer.md)

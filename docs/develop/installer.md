# 桌面壳与安装器

两个独立 Electron 应用：`electron/` 是运行时的桌面壳，`installer/` 是分发用的图形安装器。前端见 [前端开发](frontend.md)，后端打包脚本是根目录的 `main.spec`。

## 桌面壳（`electron/`）

```text
electron/
├─ main.js        # 主进程：窗口、单实例锁、GPU 降级、sidecar、内置浏览器 IPC
├─ preload.js     # contextBridge 暴露 window.purrcat
└─ api-port.cjs   # 端口选择与冲突探测
```

- 窗口统一加载 `http://127.0.0.1:<apiPort>/minimal/`，开发与生产同一条路径。
- 内置浏览器用 `WebContentsView`，属于原生层，永远盖在 DOM 之上；相关能力走 `browser:*` IPC。
- 后端是 sidecar：开发时 `uv run python main.py`，打包后是可执行文件，位置为 `resources/backend/main.exe`。
- 控制口信息写到 `~/.purrcat/run/control.json`，供外部进程发现端口与令牌。
- 安全约束：必须 `contextIsolation: true` + `contextBridge`，禁止 `nodeIntegration`。
- 禁用 GPU 等降级开关在启动参数中处理；改动后至少验证一次冷启动。

## 后端打包（`main.spec`）

```powershell
uv run pyinstaller main.spec    # 产出 dist/main
```

- 把项目根加入 `sys.path`，再用 `collect_all('src')` 收集源码内的数据文件。
- `datas` 必须包含 `ui/web-minimal`（宿主与插件）与 `scripts/acp_relay.py`（启动时部署到 `~/.purrcat/bin/`）。
- `chromadb`、`tokenizers`、`onnxruntime` 存在大量动态导入，必须 `collect_all`，否则记忆功能会在运行时空表。
- Windows 额外收集 `winpty`（含 `winpty-agent.exe` / `OpenConsole.exe`），漏掉会导致终端 PTY 初始化失败。
- 显式 `excludes` 掉 torch、transformers、playwright、opencv 等重依赖；UPX 必须关闭，否则原生 DLL 会被压坏。

## 桌面分发（`package.json` 的 `build` 段）

```powershell
npm run dist    # electron-builder，输出 release/
```

- `files` 只打包 `electron/**/*` 与 `package.json`。
- `extraResources` 把 `dist/main` 映射为应用内的 `backend`，即运行时 `resources/backend/main.exe`。
- Windows 产物为 NSIS 安装包 `PurrCat-Setup-<version>.exe`，允许用户改安装目录，并创建桌面快捷方式。
- 顺序不能颠倒：先 `pyinstaller` 产出后端，再 `electron-builder` 打包。

## 独立安装器（`installer/`）

`npm run installer:dev` 以开发模式启动；它本身也是一个 Electron 应用（`contextIsolation: true`，无菜单，无边框窗口）。

```text
installer/
├─ main.js        # 安装流程编排
├─ preload.js     # 暴露安装相关 IPC
├─ renderer/      # 安装向导界面
└─ assets/        # 图标
```

安装流程：

1. 采集安装目录与数据目录（`data_root`），逐项校验路径合法性与磁盘空间，要求至少 500MB 可用。
2. 先把 `data_root` 写入 `~/.purrcat/settings.json`，后续大文件（向量模型等）才会落到用户选择的盘。
3. 通过 `resolveInstallScript()` 找到 `install.ps1`（依次尝试 `resources/install.ps1`、仓库根、当前工作目录），以 PowerShell 启动，注入 `PURRCAT_HOME` 等环境变量，流式读取 stdout/stderr 并通过 `installer:event` 回报进度。
4. 可选配置模型连接（`installer:test-model` / `installer:save-model`）。
5. 结束后创建桌面与开始菜单快捷方式（`shell.writeShortcutLink` + `wscript.exe` 启动脚本），并回报失败项。

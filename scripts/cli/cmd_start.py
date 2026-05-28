"""PurrCat start command - Launch PurrCat application"""

import os
import subprocess
import sys

CONDA_CMD = "conda.bat" if os.name == "nt" else "conda"
NPM_CMD = "npm.cmd" if os.name == "nt" else "npm"

def _get_project_root():
    """Get the project root directory (parent of scripts/)"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_start(webui=False):
    """Start PurrCat application"""
    print("Starting PurrCat...")
    print("Press [Ctrl+C] to safely close.\n")

    project_root = _get_project_root()
    main_script = os.path.join(project_root, "main.py")

    # 构建后端启动的基础命令
    backend_cmd = [
        CONDA_CMD,
        "run",
        "--no-capture-output",
        "-n",
        "PurrCat",
        "python",
        main_script,
    ]

    ui_process = None

    # 如果启用了 WebUI 模式
    if webui:
        # 自动屏蔽 TUI 并开启 API 服务
        backend_cmd.extend(["--api", "--headless"])

        ui_dir = os.path.join(project_root, "ui")
        print("[*] Launching Web UI (npm run dev)...")
        try:
            # 采用 Popen 在后台拉起前端，与后端共享当前终端的 stdout
            ui_process = subprocess.Popen(
                [NPM_CMD, "run", "dev"],
                cwd=ui_dir
            )
        except FileNotFoundError:
            print("❌ 未找到 npm 命令，请检查 Node.js 是否已安装并配置了环境变量。")
            sys.exit(1)

    try:
        # 阻塞执行后端主进程
        subprocess.run(backend_cmd, check=True, cwd=project_root)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\nShutting down PurrCat...")
    finally:
        # 捕获到退出信号时，连带前端的 Vite 进程一起清理掉
        if ui_process:
            print("Shutting down Web UI...")
            ui_process.terminate()
            ui_process.wait()
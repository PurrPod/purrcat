"""PurrCat start command - Launch PurrCat application"""

import os
import subprocess
import sys

UV_CMD = "uv.exe" if os.name == "nt" else "uv"
NPM_CMD = "npm.cmd" if os.name == "nt" else "npm"


def _get_project_root():
    """Get the project root directory (parent of scripts/)"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _check_and_install_browser():
    """Check if Playwright Chromium is installed, install if not"""
    print("Checking Playwright browser...")
    project_root = _get_project_root()

    try:
        result = subprocess.run(
            [UV_CMD, "run", "playwright", "install", "--dry-run", "chromium"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=60,
        )

        if result.returncode != 0 or "chromium" in result.stdout.lower():
            print("Playwright Chromium not found. Installing...")
            install_result = subprocess.run(
                [UV_CMD, "run", "playwright", "install", "chromium"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=project_root,
            )
            for line in install_result.stdout.split("\n"):
                if line.strip():
                    print(f"  {line}")
            if install_result.returncode == 0:
                print("✅ Playwright Chromium installed successfully!")
            else:
                print("❌ Failed to install Playwright Chromium.")
                print("Please run 'purrcat setup' to complete the installation.")
        else:
            print("✅ Playwright Chromium is ready.")
    except subprocess.TimeoutExpired:
        print("⏱️ Browser check timed out, skipping...")
    except Exception as e:
        print(f"⚠️ Error checking browser: {e}")


def run_start(tui=False):
    """Start PurrCat application"""
    print("Starting PurrCat...")
    print("Press [Ctrl+C] to safely close.\n")

    _check_and_install_browser()
    print("")

    project_root = _get_project_root()
    main_script = os.path.join(project_root, "main.py")

    # Base command to start the backend
    backend_cmd = [
        UV_CMD,
        "run",
        "python",
        main_script,
    ]

    ui_process = None

    # 默认启动 WebUI 模式（除非指定了 tui）
    if not tui:
        # 自动屏蔽 TUI 并开启 API 服务
        backend_cmd.extend(["--api", "--headless"])

        ui_dir = os.path.join(project_root, "ui")
        print("[*] Launching Web UI (npm run dev)...")
        try:
            # 采用 Popen 在后台拉起前端，与后端共享当前终端的 stdout
            ui_process = subprocess.Popen([NPM_CMD, "run", "dev"], cwd=ui_dir)
        except FileNotFoundError:
            print(
                "❌ npm command not found. Please ensure Node.js is installed and added to your PATH."
            )
            sys.exit(1)
    else:
        print("[*] Launching Terminal UI (TUI) mode...")

    try:
        # 阻塞执行后端主进程
        subprocess.run(backend_cmd, check=True, cwd=project_root)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\nShutting down PurrCat...")
    finally:
        # Clean up the frontend Vite process when an exit signal is caught
        if ui_process:
            print("Shutting down Web UI...")
            ui_process.terminate()
            ui_process.wait()

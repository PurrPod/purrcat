"""PurrCat setup command - Cross-platform environment setup"""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

UV_CMD = "uv.exe" if os.name == "nt" else "uv"


def _get_project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_cmd(command, shell=False, check=True, cwd=None):
    cmd_str = " ".join(command) if isinstance(command, list) else command
    print(f"$ {cmd_str}")
    encoding = "gbk" if sys.platform == "win32" else "utf-8"
    process = subprocess.Popen(
        command,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=encoding,
        errors="replace",
        bufsize=1,
        cwd=cwd,
    )
    for line in process.stdout:
        print(line, end="")
    process.wait()
    if check and process.returncode != 0:
        sys.exit(process.returncode)
    return process.returncode == 0


def _check_docker():
    """检查 Docker CLI 存在且 daemon 在运行"""
    from src.utils.sandbox_setup import docker_cmd, check_docker_running

    docker = docker_cmd()
    if not docker:
        print("  [x] Docker not detected. Please install Docker Desktop first.")
        print("      Guide: https://docs.docker.com/get-docker/")
        sys.exit(1)

    print(f"  [*] Detected Docker CLI: {docker}")

    if not check_docker_running(docker):
        print("  [x] Docker service not running. Please start Docker Desktop.")
        sys.exit(1)

    print("  [*] Docker engine is running.")


def _save_engine_preference(engine: str):
    """Save engine preference to global config (统一写 docker，兼容旧字段)"""
    from src.utils.config import PURRCAT_DIR

    global_config_dir = Path(PURRCAT_DIR)
    global_config_file = global_config_dir / "settings.json"

    global_config_dir.mkdir(parents=True, exist_ok=True)

    try:
        if global_config_file.exists():
            with open(global_config_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
        else:
            settings = {}

        settings["sandbox_engine"] = engine

        with open(global_config_file, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)

        print(f"[*] Engine preference saved: {engine}")
    except Exception as e:
        print(f"[!] Failed to save engine preference: {e}")


def _get_sandbox_choice():
    print("")
    print("[Sandbox Config] Sandbox variant:")
    print("  1. Lightweight (No browser/ffmpeg, faster download)")
    print("  2. Full (Includes Chromium, ffmpeg, etc.)")
    choice = input("Enter 1 or 2 (Default is 1): ").strip() or "1"
    return "full" if choice == "2" else "light"


def _get_mirror_choice():
    print("")
    print("[Network Config] APT mirror:")
    print("  1. Global (deb.debian.org)")
    print("  2. China (mirrors.aliyun.com)")
    choice = input("Enter 1 or 2 (Default is 1): ").strip() or "1"
    return "mirrors.aliyun.com" if choice == "2" else "deb.debian.org"


def _get_sandbox_source():
    print("")
    print("[Sandbox Image] Get image from:")
    print("  1. Pull from ghcr.io (Recommended, faster)")
    print("  2. Build locally from Dockerfile")
    choice = input("Enter 1 or 2 (Default is 1): ").strip() or "1"
    return "pull" if choice == "1" else "build"


def _setup_uv():
    print("")
    print("Configuring PurrCat environment with uv...")
    project_root = _get_project_root()
    success = _run_cmd([UV_CMD, "sync"], shell=False, check=False, cwd=project_root)
    if not success:
        print("Error: uv sync failed! Please check your network or python version.")
        sys.exit(1)
    print("uv environment configured successfully!")


def _get_webui_choice():
    print("")
    print("[WebUI Config] Install WebUI dependencies (npm)?")
    print("  1. Yes")
    print("  2. No")
    choice = input("Enter 1 or 2 (Default is 1): ").strip() or "1"
    return choice == "1"


def _install_webui():
    print("")
    print("Installing WebUI dependencies...")
    project_root = _get_project_root()
    ui_dir = os.path.join(project_root, "ui")
    if not os.path.exists(ui_dir):
        print(f"Warning: UI directory not found at {ui_dir}")
        return
    success = _run_cmd("npm install", shell=True, check=False, cwd=ui_dir)
    if success:
        print("WebUI dependencies installed successfully!")
    else:
        print("Warning: WebUI installation may have failed!")


def _ensure_embedding_model_blocking():
    """setup 命令同步等待嵌入模型下载完成"""
    import time

    from src.utils.embedding_setup import (
        ensure_embedding_model,
        _downloading_flag,
        EMBEDDING_DIR,
        _model_exists,
    )

    print("")
    print("=== Embedding Model ===")
    if _model_exists(EMBEDDING_DIR):
        print(f"[*] Embedding model already exists at {EMBEDDING_DIR}")
        return

    ensure_embedding_model()
    # 同步等待下载线程完成
    while _downloading_flag.is_set():
        time.sleep(1)
    if _model_exists(EMBEDDING_DIR):
        print("[+] Embedding model ready!")
    else:
        print("[!] Embedding model not ready. You can retry: purrcat setup")


def _setup_sandbox_interactive():
    """setup 命令的交互式沙盒配置"""
    from src.utils.sandbox_setup import interactive_build_sandbox, check_image_exists
    from src.utils.sandbox_setup import SANDBOX_IMAGE_TAG, docker_cmd

    print("")
    print("=== Docker Sandbox ===")
    _check_docker()
    _save_engine_preference("docker")

    if check_image_exists(docker_cmd(), SANDBOX_IMAGE_TAG):
        print(f"[*] Sandbox image already exists: {SANDBOX_IMAGE_TAG}")
        print("[*] Skip sandbox build.")
        return

    variant = _get_sandbox_choice()
    source = _get_sandbox_source()

    if source == "pull":
        apt_mirror = None
    else:
        apt_mirror = _get_mirror_choice()

    ok = interactive_build_sandbox(
        variant=variant, apt_mirror=apt_mirror or "deb.debian.org", source=source
    )
    if not ok:
        print("")
        print("Error: Failed to get sandbox image.")
        print("Common causes:")
        print("  1. Network issues - Try build locally or use another mirror.")
        print("  2. Disk space insufficient.")
        sys.exit(1)
    print(f"Sandbox image ({variant}) ready!")


def _install_playwright_browser():
    print("")
    print("Installing Playwright Chromium browser...")
    project_root = _get_project_root()
    success = _run_cmd(
        [UV_CMD, "run", "playwright", "install", "chromium"],
        shell=False,
        check=False,
        cwd=project_root,
    )
    if success:
        print("Playwright Chromium browser installed successfully!")
    else:
        print("Warning: Playwright browser installation may have failed!")
        print("You can try running: uv run playwright install chromium")


def run_setup():
    """Main setup workflow (用户手动执行时的完整交互流程)"""
    print("Welcome to PurrCat environment setup...")
    print("==========================================")
    print("")
    print(f"Detected OS: {platform.system()}")
    print("==========================================")

    _setup_sandbox_interactive()
    print("==========================================")

    install_webui = _get_webui_choice()
    print("==========================================")

    _setup_uv()
    print("==========================================")

    _ensure_embedding_model_blocking()
    print("==========================================")

    _install_playwright_browser()
    print("==========================================")

    if install_webui:
        _install_webui()
        print("==========================================")

    print("Congratulations! PurrCat environment is ready.")
    print(
        "Next: Run 'npm run dev' (Electron desktop) from the project root to start the application."
    )
    print("Engine: Docker (sandbox)")

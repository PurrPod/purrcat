"""PurrCat setup command - Cross-platform environment setup"""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

CONDA_CMD = "conda.bat" if os.name == "nt" else "conda"


def _get_project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_cmd(command, shell=False, check=True, cwd=None):
    cmd_str = " ".join(command) if isinstance(command, list) else command
    print(f"$ {cmd_str}")
    process = subprocess.Popen(
        command,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=cwd,
    )
    for line in process.stdout:
        print(line, end="")
    process.wait()
    if check and process.returncode != 0:
        sys.exit(process.returncode)
    return process.returncode == 0


def _check_engine():
    """Check which container engines are available"""
    try:
        has_docker = subprocess.call(
            ["docker", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ) == 0
    except FileNotFoundError:
        has_docker = False

    try:
        has_podman = subprocess.call(
            ["podman", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ) == 0
    except FileNotFoundError:
        has_podman = False

    return has_docker, has_podman


def _get_engine_choice():
    """Prompt user for container engine selection with intelligent recommendation"""
    print("")
    print("[Container Engine Config] Choose your container runtime:")
    print("")

    os_name = platform.system()
    has_docker, has_podman = _check_engine()

    recommend_engine = "docker"
    recommend_reason = "Docker is the most popular container engine."

    if os_name == "Windows" and not has_docker:
        recommend_engine = "podman"
        recommend_reason = "Detected Windows without Docker Desktop. Strongly recommend lightweight Podman."
    elif os_name == "Darwin" and not has_docker:
        recommend_engine = "podman"
        recommend_reason = "Recommend lightweight Podman to save Mac memory."
    elif has_podman and not has_docker:
        recommend_engine = "podman"
        recommend_reason = "Detected Podman is already installed."
    elif has_podman and has_docker:
        recommend_engine = "docker"
        recommend_reason = "Both Docker and Podman detected. Defaulting to Docker."

    print(f"  💡 System Recommendation: {recommend_reason}")
    print("")

    engine_options = []
    if has_podman:
        engine_options.append("1. Podman (Recommended, lightweight)")
    if has_docker:
        engine_options.append("2. Docker (Standard, requires Docker Desktop)")

    if not engine_options:
        print("  ⚠️  No container engine detected. Will try to install Podman...")
        return "podman", True

    print("  Available options:")
    for opt in engine_options:
        print(f"    {opt}")

    default = "1" if recommend_engine == "podman" else "2"
    choice = input(f"Enter choice [default: {default}]: ").strip() or default

    selected_engine = "podman" if choice == "1" else "docker"
    should_install = False

    if selected_engine == "podman" and not has_podman:
        should_install = True
    elif selected_engine == "docker" and not has_docker:
        should_install = True

    return selected_engine, should_install


def _install_podman():
    """Install Podman by delegating to the robust setup_env script"""
    print("")
    print("Installing Podman...")

    try:
        from scripts.setup_env import setup as full_podman_setup

        success, message = full_podman_setup()
        if success:
            print(f"✅ {message}")
        else:
            print(f"\n❌ Podman 自动安装/配置失败: {message}")
            print("请手动参考官方文档安装： https://podman.io/getting-started/installation")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Podman 安装脚本执行失败: {e}")
        print("请手动参考官方文档安装： https://podman.io/getting-started/installation")
        sys.exit(1)


def _save_engine_preference(engine: str):
    """Save engine preference to global config"""
    global_config_dir = Path.home() / ".purrcat"
    global_config_file = global_config_dir / "settings.json"

    global_config_dir.mkdir(parents=True, exist_ok=True)

    try:
        if global_config_file.exists():
            with open(global_config_file, "r", encoding="utf-8") as f:
                settings = json.load(f) if hasattr(__import__('json'), 'load') else {}
        else:
            settings = {}

        settings["sandbox_engine"] = engine

        with open(global_config_file, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)

        print(f"✅ Engine preference saved to global config: {engine}")
    except Exception as e:
        print(f"⚠️ Failed to save engine preference: {e}")


def _check_engine_running(engine):
    """Check if the selected engine is running"""
    print(f"Checking {engine} service...")

    if engine == "podman":
        result = subprocess.call(
            ["podman", "machine", "list"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if result != 0:
            print("Podman machine not running. Initializing...")
            subprocess.call(["podman", "machine", "init"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.call(["podman", "machine", "start"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("Podman machine initialized and started.")
        else:
            print("Podman is ready.")
    else:
        result = subprocess.call(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if result != 0:
            print("Error: Docker not detected or service not running.")
            sys.exit(1)
        print("Docker engine is running.")


def _get_sandbox_choice():
    """Prompt user for sandbox type selection"""
    print("")
    print("[Sandbox Config] Do you want a lightweight sandbox or a full sandbox?")
    print("  The full docker includes a browser, ffmpeg.")
    print("  1. Lightweight Sandbox (No browser/ffmpeg, faster to build)")
    print("  2. Full Sandbox (Includes Chromium, ffmpeg, etc.)")
    choice = input("Enter 1 or 2 (Default is 1): ").strip() or "1"
    return "Dockerfile.full" if choice == "2" else "Dockerfile.light"


def _get_mirror_choice():
    """Prompt user for network mirror selection"""
    print("")
    print("[Network Config] Are you available to the external network?")
    print("  1. Yes (Global / Official Source)")
    print("  2. No (China Region / Aliyun Mirror)")
    choice = input("Enter 1 or 2 (Default is 1): ").strip() or "1"
    return "mirrors.aliyun.com" if choice == "2" else "deb.debian.org"


def _build_sandbox(dockerfile, apt_mirror, engine):
    """Build sandbox image using selected engine"""
    print("")
    print(f"Building sandbox image using {engine} with {apt_mirror} and {dockerfile}...")
    print("Note: First pull may take a few minutes, please wait...")

    project_root = _get_project_root()

    build_cmd = [
        engine,
        "build",
        "-f",
        dockerfile,
        "-t",
        "my_agent_env:latest",
        "--build-arg",
        f"APT_MIRROR={apt_mirror}",
        ".",
    ]

    success = _run_cmd(build_cmd, shell=False, check=False, cwd=project_root)

    if not success:
        print("")
        print(f"Error: {engine.capitalize()} image build failed!")
        print("Common causes:")
        print("  1. Network issues - Check your proxy or try the other mirror.")
        print("  2. Docker/Podman disk space insufficient.")
        sys.exit(1)

    print(f"{engine.capitalize()} image built successfully!")


def _setup_conda():
    """Configure Conda environment"""
    print("")
    print("Configuring PurrCat Conda environment...")

    project_root = _get_project_root()
    env_file = os.path.join(project_root, "environment.yml")

    check_env_cmd = [CONDA_CMD, "env", "list"]
    result = subprocess.run(check_env_cmd, capture_output=True, text=True)

    if "PurrCat" in result.stdout:
        print("Environment 'PurrCat' already exists, trying to update dependencies...")
        update_success = _run_cmd(
            [CONDA_CMD, "env", "update", "-f", env_file],
            shell=False,
            check=False,
            cwd=project_root,
        )
        if not update_success:
            print("Update failed, trying to create environment...")
            _run_cmd(
                [CONDA_CMD, "env", "create", "-f", env_file],
                shell=False,
                cwd=project_root,
            )
    else:
        print("Creating new Conda environment...")
        _run_cmd(
            [CONDA_CMD, "env", "create", "-f", env_file], shell=False, cwd=project_root
        )

    print("Conda environment configured successfully!")


def _get_webui_choice():
    """Prompt user for web UI installation"""
    print("")
    print("[WebUI Config] Do you want to install WebUI?")
    print("  This will install npm dependencies for the web interface.")
    print("  1. Yes (Install WebUI dependencies)")
    print("  2. No (Skip WebUI installation)")
    choice = input("Enter 1 or 2 (Default is 1): ").strip() or "1"
    return choice == "1"


def _install_webui():
    """Install WebUI npm dependencies"""
    print("")
    print("Installing WebUI dependencies...")

    project_root = _get_project_root()
    ui_dir = os.path.join(project_root, "ui")

    if not os.path.exists(ui_dir):
        print(f"Warning: UI directory not found at {ui_dir}")
        print("WebUI installation skipped.")
        return

    success = _run_cmd("npm install", shell=True, check=False, cwd=ui_dir)

    if success:
        print("WebUI dependencies installed successfully!")
    else:
        print("Warning: WebUI installation may have failed!")


def _download_embedding_model():
    """Download embedding model using setup_emb.py"""
    print("")
    print("Downloading Embedding model...")

    project_root = _get_project_root()
    setup_emb_script = os.path.join(project_root, "scripts", "setup_emb.py")

    success = _run_cmd(
        [CONDA_CMD, "run", "-n", "PurrCat", "python", setup_emb_script],
        shell=False,
        check=False,
    )

    if not success:
        print("Warning: Embedding model download may have failed!")
        sys.exit(1)

    print("Model resources ready!")


def run_setup():
    """Main setup workflow"""
    print("Welcome to PurrCat environment setup...")
    print("==========================================")
    print("")
    print(f"Detected OS: {platform.system()}")
    print("==========================================")

    selected_engine, should_install = _get_engine_choice()

    if should_install:
        _install_podman()

    _save_engine_preference(selected_engine)
    _check_engine_running(selected_engine)

    print("==========================================")

    dockerfile = _get_sandbox_choice()
    apt_mirror = _get_mirror_choice()
    install_webui = _get_webui_choice()

    _build_sandbox(dockerfile, apt_mirror, selected_engine)
    print("==========================================")

    _setup_conda()
    print("==========================================")

    _download_embedding_model()
    print("==========================================")

    if install_webui:
        _install_webui()
        print("==========================================")

    print("Congratulations! PurrCat environment is ready.")
    print(f"Next: Run 'purrcat start' to start the application.")
    print(f"Engine in use: {selected_engine} (saved to ~/.purrcat/settings.json)")
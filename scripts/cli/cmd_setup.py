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


def _check_engine():
    """Check which container engines are available"""
    encoding = "gbk" if sys.platform == "win32" else "utf-8"

    try:
        result = subprocess.run(
            ["docker", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            encoding=encoding,
            errors="replace",
        )
        has_docker = result.returncode == 0
    except FileNotFoundError:
        has_docker = False

    try:
        result = subprocess.run(
            ["podman", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            encoding=encoding,
            errors="replace",
        )
        has_podman = result.returncode == 0
    except FileNotFoundError:
        has_podman = False

    return has_docker, has_podman


def _determine_engine():
    """Auto determine container engine based on availability"""
    print("")
    print("[Container Engine Config] Checking local environment...")

    has_docker, has_podman = _check_engine()

    if has_docker:
        print("  ✅ Detected Docker, will use Docker as container engine.")
        return "docker"
    elif has_podman:
        print("  ✅ Detected Podman, will use Podman as container engine.")
        return "podman"
    else:
        print(
            "  ❌ Docker not detected. Please install Docker first according to the tutorial."
        )
        sys.exit(1)


def _save_engine_preference(engine: str):
    """Save engine preference to global config"""
    global_config_dir = Path.home() / ".purrcat"
    global_config_file = global_config_dir / "settings.json"

    global_config_dir.mkdir(parents=True, exist_ok=True)

    try:
        if global_config_file.exists():
            with open(global_config_file, "r", encoding="utf-8") as f:
                settings = json.load(f) if hasattr(__import__("json"), "load") else {}
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
            stderr=subprocess.DEVNULL,
        )
        if result != 0:
            print("Podman machine not running. Initializing...")
            subprocess.call(
                ["podman", "machine", "init"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.call(
                ["podman", "machine", "start"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print("Podman machine initialized and started.")
        else:
            print("Podman is ready.")
    else:
        result = subprocess.call(
            ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
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


def _get_sandbox_source():
    """Prompt user for sandbox image source"""
    print("")
    print("[Sandbox Image] How to get the sandbox image?")
    print("  1. Pull from ghcr.io (recommended, faster)")
    print("  2. Build locally (requires Dockerfile build)")
    choice = input("Enter 1 or 2 (Default is 1): ").strip() or "1"
    return choice == "1"


def _pull_sandbox(dockerfile, engine):
    """Pull pre-built sandbox image from ghcr.io"""
    variant = "light" if "light" in dockerfile else "full"
    image = f"ghcr.io/purrpod/purrcat-sandbox:{variant}"

    print("")
    print(f"Pulling sandbox image from {image}...")
    print("Note: First pull may take a few minutes depending on your network.")

    success = _run_cmd([engine, "pull", image], shell=False, check=False)

    if not success:
        print("")
        print("Error: Failed to pull sandbox image!")
        print("Common causes:")
        print("  1. Network issues - Check your connection")
        print("  2. ghcr.io not accessible in your region")
        sys.exit(1)

    # Retag as my_agent_env:latest so the rest of the code works unchanged
    _run_cmd([engine, "tag", image, "my_agent_env:latest"], shell=False, check=False)
    print("Sandbox image pulled and tagged as my_agent_env:latest!")


def _build_sandbox(dockerfile, apt_mirror, engine):
    """Build sandbox image using selected engine"""
    print("")
    print(
        f"Building sandbox image using {engine} with {apt_mirror} and {dockerfile}..."
    )
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


def _setup_uv():
    """Configure environment using uv"""
    print("")
    print("Configuring PurrCat environment with uv...")
    project_root = _get_project_root()

    # Resolve and install all dependencies in one go using uv
    success = _run_cmd([UV_CMD, "sync"], shell=False, check=False, cwd=project_root)

    if not success:
        print("Error: uv sync failed! Please check your network or python version.")
        sys.exit(1)
    print("uv environment configured successfully!")


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
        [UV_CMD, "run", "python", setup_emb_script],
        shell=False,
        check=False,
        cwd=project_root,
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

    # Auto-detect local container engine
    selected_engine = _determine_engine()

    _save_engine_preference(selected_engine)
    _check_engine_running(selected_engine)

    print("==========================================")

    dockerfile = _get_sandbox_choice()
    pull_from_ghcr = _get_sandbox_source()

    if pull_from_ghcr:
        _pull_sandbox(dockerfile, selected_engine)
    else:
        apt_mirror = _get_mirror_choice()
        _build_sandbox(dockerfile, apt_mirror, selected_engine)

    install_webui = _get_webui_choice()
    print("==========================================")

    _setup_uv()
    print("==========================================")

    _download_embedding_model()
    print("==========================================")

    if install_webui:
        _install_webui()
        print("==========================================")

    print("Congratulations! PurrCat environment is ready.")
    print("Next: Run 'purrcat start' to start the application.")
    print(f"Engine in use: {selected_engine} (saved to ~/.purrcat/settings.json)")

"""PurrCat setup command - Cross-platform environment setup"""

import subprocess
import sys
import os

CONDA_CMD = "conda.bat" if os.name == "nt" else "conda"


def _get_project_root():
    """Get the project root directory (parent of scripts/)"""
    # __file__ = scripts/cli/cmd_setup.py
    # 向上3层: cmd_setup.py -> cli/ -> scripts/ -> 项目根目录
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_cmd(command, shell=False, check=True, cwd=None):
    """Helper execute system command and print output in real-time"""
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


def _check_docker():
    """Check if Docker is available and running"""
    print("Checking Docker service...")
    result = subprocess.call(
        ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    if result != 0:
        print(
            "Error: Docker not detected or service not running. Please start Docker and try again."
        )
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


def _build_docker(dockerfile, apt_mirror):
    """Build Docker sandbox image"""
    print("")
    print(f"Building Docker sandbox image using {apt_mirror} and {dockerfile}...")
    print("Note: First pull may take a few minutes, please wait...")

    project_root = _get_project_root()
    success = _run_cmd(
        [
            "docker",
            "build",
            "-f",
            dockerfile,
            "-t",
            "my_agent_env:latest",
            "--build-arg",
            f"APT_MIRROR={apt_mirror}",
            ".",
        ],
        shell=False,
        check=False,
        cwd=project_root,
    )

    if not success:
        print("")
        print("Error: Docker image build failed completely!")
        print("Common causes:")
        print("  1. Network issues - Check your proxy or try the other mirror.")
        print("  2. Docker disk space insufficient.")
        print("  3. Not logged into Docker Hub, or anonymous pull limit reached.")
        sys.exit(1)

    print("Docker image built successfully!")


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

    success = _run_cmd(["npm", "install"], shell=False, check=False, cwd=ui_dir)

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

    _check_docker()
    print("==========================================")

    dockerfile = _get_sandbox_choice()
    apt_mirror = _get_mirror_choice()
    install_webui = _get_webui_choice()

    _build_docker(dockerfile, apt_mirror)
    print("==========================================")

    _setup_conda()
    print("==========================================")

    _download_embedding_model()
    print("==========================================")

    if install_webui:
        _install_webui()
        print("==========================================")

    print("Congratulations! PurrCat environment is ready.")
    print("Next: Run 'purrcat start' to start the TUI.")

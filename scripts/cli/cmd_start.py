"""PurrCat start command - Launch PurrCat application"""

import subprocess
import sys
import os

CONDA_CMD = "conda.bat" if os.name == "nt" else "conda"


def _get_project_root():
    """Get the project root directory (parent of scripts/)"""
    # __file__ = scripts/cli/cmd_start.py
    # 向上3层: cmd_start.py -> cli/ -> scripts/ -> 项目根目录
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_start(headless=False):
    """Start PurrCat application"""
    print("Starting PurrCat...")
    print("Press [Ctrl+C] to safely close.")
    print("")

    project_root = _get_project_root()
    main_script = os.path.join(project_root, "main.py")

    cmd = [
        CONDA_CMD,
        "run",
        "--no-capture-output",
        "-n",
        "PurrCat",
        "python",
        main_script,
    ]
    if headless:
        cmd.append("--headless")

    try:
        subprocess.run(cmd, check=True, cwd=project_root)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\nShutting down PurrCat...")

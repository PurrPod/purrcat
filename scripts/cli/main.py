"""PurrCat CLI - Cross-platform AI Agent Framework"""
import argparse
import sys
import os

from scripts.cli.cmd_init import run_init
from scripts.cli.cmd_install import run_install
from scripts.cli.cmd_setup import run_setup
from scripts.cli.cmd_start import run_start
from scripts.cli.cmd_update import run_update


def _setup_path():
    """Set up Python path for cross-platform compatibility"""
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)


def cmd_help():
    """Print help menu with ASCII Cat Logo"""
    cat_logo = r"""
      /\_/\
     ( O_O )
      |>  <|⟆

PurrCat CLI - Cross-platform AI Agent Framework
===============================================
    """
    print(cat_logo)
    print("Version: v2026.05.15")
    print("")
    print("Usage: purrcat <command> [options]")
    print("")
    print("Commands:")
    print("  setup   - Initialize environment (Conda, Docker, Models)")
    print("  init    - Generate .purrcat config templates")
    print("  install - Install extensions (skill, node, graph)")
    print("  update  - Update PurrCat to the latest version from GitHub")
    print("  start   - Start PurrCat (append --headless for background run)")
    print("")
    print("Examples:")
    print("  purrcat setup")
    print("  purrcat init --force")
    print("")
    print("  # Install official extensions from PurrPod")
    print("  purrcat install node web_search")
    print("  purrcat install graph daily_summary")
    print("")
    print("  # Install third-party skill from any GitHub repo")
    print("  purrcat install skill https://github.com/user/repo/tree/main/path/to/skill")
    print("")
    print("  purrcat update")
    print("  purrcat update --version=\"2026.05.15\"")
    print("  purrcat start --headless")
    print("")
    print("Docs:     https://purrpod.github.io/")
    print("GitHub:   https://github.com/PurrPod/purrcat")
    print("License:  GNU GPL-3.0")
    print("")


def main():
    _setup_path()

    parser = argparse.ArgumentParser(
        prog="purrcat",
        description="PurrCat - Cross-platform AI Agent Framework",
        add_help=False
    )
    parser.add_argument("command", nargs="?", default="help", choices=["init", "help", "install", "setup", "start", "update"])
    parser.add_argument("--force", "-f", action="store_true", help="Force overwrite existing files")
    parser.add_argument("--headless", action="store_true", help="Run in background (for start command)")
    parser.add_argument("--help", "-h", action="store_true", help="Show this help message")
    parser.add_argument("--version", type=str, help="Specify release version to update to (e.g., 2026.05.15 or v2026.05.15)")
    parser.add_argument("ext_type", nargs="?", choices=["skill", "node", "graph"], help="Type of extension to install")
    parser.add_argument("source", nargs="?", help="Name or GitHub URL")

    args, _ = parser.parse_known_args()

    if args.help or args.command == "help":
        cmd_help()
    elif args.command == "init":
        run_init(force=args.force)
    elif args.command == "install":
        if not args.ext_type or not args.source:
            print("X Error: install requires both <ext_type> and <source>")
            print("  Example: purrcat install skill https://github.com/user/repo/tree/main/skills/my_skill")
            sys.exit(1)
        run_install(args.ext_type, args.source)
    elif args.command == "setup":
        run_setup()
    elif args.command == "update":
        run_update(target_version=args.version)
    elif args.command == "start":
        run_start(headless=args.headless)
    else:
        cmd_help()


if __name__ == "__main__":
    _setup_path()
    main()

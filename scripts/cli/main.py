"""PurrCat CLI - desktop launcher"""

import os
import sys

from scripts.cli.cmd_desktop import run as run_desktop


def _setup_path():
    """Set up Python path for cross-platform compatibility"""
    PROJECT_ROOT = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)


def main():
    _setup_path()

    argv = sys.argv[1:]
    if argv and argv[0] == "desktop":
        run_desktop(argv[1:])
        return

    print("Usage: purrcat desktop <start | update>")
    if argv:
        print(f"Unknown command: {argv[0]}")
        sys.exit(1)


if __name__ == "__main__":
    main()

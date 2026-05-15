"""PurrCat CLI - Backward compatibility shim"""
import sys
import os

# __file__ = scripts/cli.py，向上两层是项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.cli.main import main

if __name__ == "__main__":
    main()
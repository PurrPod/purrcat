# main.py
import sys
from tui.app import CatInCupApp

def main():
    # 直接拉起 TUI
    app = CatInCupApp()
    app.run()

if __name__ == "__main__":
    main()
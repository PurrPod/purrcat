# main.py
import sys
from tui.app import CatInCupTUI

def main():
    # 直接拉起 TUI
    app = CatInCupTUI()
    app.run()

if __name__ == "__main__":
    main()
import warnings
# 抑制无关警告
warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine 'ExpiringCache._start_clear_cron' was never awaited")
warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated as an API")
from tui.app import PurrCatTUI
def main():
    # 直接拉起 TUI
    app = PurrCatTUI()
    app.run()

if __name__ == "__main__":
    main()
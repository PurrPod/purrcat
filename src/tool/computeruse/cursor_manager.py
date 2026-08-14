"""
Windows 专属 AI 鼠标接管指示器 (恒定大光标版)
"""

import time
import threading
import platform
import ctypes
import os

_last_ai_action_time = 0
_is_ai_cursor = False
_watcher_thread = None
_lock = threading.Lock()

# AI 操作结束后多少秒无新动作则恢复默认光标
IDLE_TIMEOUT = 10

# --- Windows API 常量 ---
SPI_SETCURSORS = 0x0057
IMAGE_CURSOR = 2
LR_LOADFROMFILE = 0x00000010

# 系统必须被覆盖的光标状态列表
TARGET_CURSOR_IDS = [
    32512,  # OCR_NORMAL (普通箭头)
    32513,  # OCR_IBEAM (文本输入用的 'I' 标)
    32514,  # OCR_WAIT (纯加载转圈/沙漏)
    32649,  # OCR_HAND (手指点击标)
    32650,  # OCR_APPSTARTING (箭头带转圈/后台加载)
]


def _set_ai_cursor_all():
    """将系统中所有常见状态的光标全部替换为 AI 光标"""
    user32 = ctypes.windll.user32

    # 加载自定义的 AI 光标文件
    cur_path = os.path.join(os.path.dirname(__file__), "ai.cur")
    base_h_cursor = user32.LoadImageW(0, cur_path, IMAGE_CURSOR, 0, 0, LR_LOADFROMFILE)

    if not base_h_cursor:
        base_h_cursor = user32.LoadCursorW(0, 32515)

    if not base_h_cursor:
        return

    for cursor_id in TARGET_CURSOR_IDS:
        h_copy = user32.CopyImage(base_h_cursor, IMAGE_CURSOR, 0, 0, 0)
        if h_copy:
            user32.SetSystemCursor(h_copy, cursor_id)


def restore_normal_cursor():
    """手动恢复 Windows 默认光标（需要时可主动调用）"""
    ctypes.windll.user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)


def _cursor_watcher_loop():
    """后台监控线程 - 超过 IDLE_TIMEOUT 秒无 AI 动作则恢复默认光标"""
    global _is_ai_cursor
    while True:
        time.sleep(1)
        with _lock:
            if _is_ai_cursor and (time.time() - _last_ai_action_time) > IDLE_TIMEOUT:
                restore_normal_cursor()
                _is_ai_cursor = False


def notify_ai_active():
    """每次 AI 操作时调用"""
    global _last_ai_action_time, _is_ai_cursor, _watcher_thread

    if platform.system().lower() != "windows":
        return

    with _lock:
        _last_ai_action_time = time.time()
        if not _is_ai_cursor:
            _set_ai_cursor_all()
            _is_ai_cursor = True

        if _watcher_thread is None:
            _watcher_thread = threading.Thread(target=_cursor_watcher_loop, daemon=True)
            _watcher_thread.start()

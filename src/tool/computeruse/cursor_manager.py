"""
Windows 专属 AI 鼠标接管指示器 (全状态覆盖流畅版)
"""

import time
import threading
import platform
import ctypes
import os

_last_ai_action_time = 0
_is_ai_cursor = False
_watcher_thread = None
_lock = threading.Lock()  # 增加线程锁，防止多线程调用卡顿

# --- Windows API 常量 ---
SPI_SETCURSORS = 0x0057
IMAGE_CURSOR = 2
LR_LOADFROMFILE = 0x00000010

# 系统必须被覆盖的光标状态列表（解决变成 I 标、加载标的问题）
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

    # 如果自定义光标加载失败，降级使用系统自带的十字准星 (IDC_CROSS = 32515)
    if not base_h_cursor:
        base_h_cursor = user32.LoadCursorW(0, 32515)

    if not base_h_cursor:
        return  # 如果加载失败直接退出，防止程序崩溃

    # 遍历替换所有状态
    for cursor_id in TARGET_CURSOR_IDS:
        # ⚠️ 核心技巧：SetSystemCursor 会"吃掉（销毁）"传入的句柄。
        # 如果不 CopyImage 复制出新句柄，第二次循环就会报错闪退或卡死。
        h_copy = user32.CopyImage(base_h_cursor, IMAGE_CURSOR, 0, 0, 0)
        if h_copy:
            user32.SetSystemCursor(h_copy, cursor_id)


def _restore_normal_cursor():
    """恢复 Windows 默认的所有光标"""
    ctypes.windll.user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)


def _cursor_watcher_loop():
    """后台监控线程"""
    global _is_ai_cursor
    while True:
        time.sleep(0.5)
        with _lock:
            if _is_ai_cursor and (time.time() - _last_ai_action_time > 15.0):
                _restore_normal_cursor()
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

import time
import pyperclip
import pyautogui
import mss
from PIL import Image
import numpy as np
from src.tool.computeruse.adapters.base import BasePlatformAdapter

try:
    from AppKit import NSWorkspace
except ImportError:
    pass

_ocr_reader = None


def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            _ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        except:
            pass
    return _ocr_reader


class MacOSAdapter(BasePlatformAdapter):
    def __init__(self):
        pyautogui.FAILSAFE = False

    def get_screen_size(self):
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            return monitor["width"], monitor["height"]

    def get_screenshot_image(self) -> Image.Image:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

    def get_ocr_elements(self, img_array) -> list:
        reader = _get_ocr_reader()
        if reader is None:
            return []
        try:
            ocr_results = reader.readtext(img_array)
            elements = []
            for (bbox, text, prob) in ocr_results:
                if prob > 0.4:
                    px1 = min([p[0] for p in bbox])
                    py1 = min([p[1] for p in bbox])
                    px2 = max([p[0] for p in bbox])
                    py2 = max([p[1] for p in bbox])
                    elements.append({"type": "[纯文本]", "text": text, "bbox": [px1, py1, px2, py2]})
            return elements
        except:
            return []

    def get_ui_tree_elements(self) -> list:
        # 简化版：macOS 用 AppleScript 批量获取结构较慢，交由 OCR 兜底
        # 实际生产中可以加入 AXUIElement 过滤，这里为演示轻量化
        return []

    def scroll(self, amount: int):
        # macOS 滚动单位较大，需要调优
        pyautogui.scroll(amount * -10)

    def move_mouse(self, x: int, y: int):
        pyautogui.moveTo(x, y, duration=0.3, tween=pyautogui.easeOutQuad)

    def click(self, x: int, y: int, button: str, clicks: int):
        self.move_mouse(x, y)
        pyautogui.click(button=button, clicks=clicks)

    def drag_mouse(self, dest_x: int, dest_y: int):
        pyautogui.dragTo(dest_x, dest_y, duration=0.5, button='left')

    def type_via_clipboard(self, text: str):
        saved = pyperclip.paste()
        try:
            pyperclip.copy(text)
            pyautogui.hotkey('command', 'v')
        finally:
            if isinstance(saved, str):
                pyperclip.copy(saved)

    def press_hotkey(self, keys: str):
        pyautogui.hotkey(*['command' if p in ['ctrl', 'control'] else p for p in keys.lower().split('+')])

    def hide_other_apps(self, keep_apps: list) -> list:
        return []
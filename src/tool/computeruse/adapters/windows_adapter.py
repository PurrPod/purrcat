import time
import pyperclip
import pyautogui
import mss
from PIL import Image
import numpy as np
from src.tool.computeruse.adapters.base import BasePlatformAdapter

_ocr_reader = None


def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            _ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        except ImportError:
            pass
    return _ocr_reader


class WindowsAdapter(BasePlatformAdapter):
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
            # 原汁原味的高清原图，交给 Executor 跑 OCR
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

    def get_ocr_elements(self, img_array) -> list:
        reader = _get_ocr_reader()
        if reader is None:
            return []

        try:
            # 此时的 img_array 是高清原图，OCR 准确率拉满
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

    def get_focused_element_info(self) -> str:
        """获取当前活动窗口"""
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return ""
            title = win32gui.GetWindowText(hwnd)
            return f"活动窗口: '{title}'"
        except Exception:
            return ""

    def get_ui_tree_elements(self) -> list:
        try:
            import pywinauto
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return []

            app = pywinauto.Application(backend="uia").connect(handle=hwnd)
            front_window = app.window(handle=hwnd)

            elements = []
            VALID_CONTROLS = ["ButtonControl", "EditControl", "MenuItemControl", "TabItemControl",
                              "ListItemControl", "HyperlinkControl", "DocumentControl"]

            def traverse(ctrl, depth=0):
                if depth > 5:
                    return
                try:
                    ctrl_type = ctrl.element_info.control_type
                    name = ctrl.element_info.name
                    # 提取 helper 文本，应对没有 name 的输入框
                    help_text = ctrl.element_info.help_text
                    text = name or help_text or ""

                    rect = ctrl.element_info.rectangle

                    if ctrl_type in VALID_CONTROLS:
                        elements.append({
                            "type": f"[{ctrl_type.replace('Control', '')}]",
                            "text": text,
                            "bbox": [rect.left, rect.top, rect.right, rect.bottom]
                        })
                    for child in ctrl.children():
                        traverse(child, depth + 1)
                except:
                    pass

            traverse(front_window)
            return elements
        except:
            return []

    def scroll(self, amount: int):
        # Windows 中 pyautogui.scroll 负数代表向下滚
        pyautogui.scroll(amount * -1)

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
            pyautogui.hotkey('ctrl', 'v')
        finally:
            if isinstance(saved, str):
                pyperclip.copy(saved)

    def press_hotkey(self, keys: str):
        pyautogui.hotkey(*[p if p != 'control' else 'ctrl' for p in keys.lower().split('+')])

    def hide_other_apps(self, keep_apps: list) -> list:
        return []
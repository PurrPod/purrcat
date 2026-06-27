import pyperclip
import pyautogui
import mss
from PIL import Image
from src.tool.computeruse.adapters.base import BasePlatformAdapter

_ocr_reader = None


def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr

            _ocr_reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
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
            for bbox, text, prob in ocr_results:
                if prob > 0.4:
                    px1 = min([p[0] for p in bbox])
                    py1 = min([p[1] for p in bbox])
                    px2 = max([p[0] for p in bbox])
                    py2 = max([p[1] for p in bbox])
                    elements.append(
                        {"type": "[纯文本]", "text": text, "bbox": [px1, py1, px2, py2]}
                    )
            return elements
        except Exception:
            return []

    def get_focused_element_info(self) -> str:
        """获取当前拥有焦点的精准控件信息（不再只有窗口标题）"""
        try:
            import win32gui

            # 1. 先获取当前活动窗口，作为兜底信息
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return ""
            app_name = win32gui.GetWindowText(hwnd)

            # 2. 尝试使用 UI Automation 获取元素级焦点
            try:
                # 引入专业的 uiautomation 库（通常比 pywinauto 查焦点更直接）
                import uiautomation as auto

                # 获取系统级当前拥有键盘焦点的控件
                focused_control = auto.GetFocusedControl()

                if focused_control:
                    ctrl_type = focused_control.ControlTypeName
                    name = focused_control.Name or ""

                    # 拼装出和 macOS 一模一样的格式，大模型最喜欢这种
                    if name:
                        return f"焦点位于: [{ctrl_type.replace('Control', '')}] '{name}' (所属应用: {app_name})"
                    else:
                        return f"焦点位于: [{ctrl_type.replace('Control', '')}] (所属应用: {app_name})"
            except ImportError:
                # 如果没装 uiautomation，也可以尝试用自带的 pywinauto 去遍历 (效率稍低)
                pass

            # 3. 如果 UIA 失败（比如遇到不支持的自绘引擎游戏），兜底返回窗口标题
            return f"活动窗口: '{app_name}'"

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
            VALID_CONTROLS = [
                "ButtonControl",
                "EditControl",
                "MenuItemControl",
                "TabItemControl",
                "ListItemControl",
                "HyperlinkControl",
                "DocumentControl",
            ]

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
                        elements.append(
                            {
                                "type": f"[{ctrl_type.replace('Control', '')}]",
                                "text": text,
                                "bbox": [rect.left, rect.top, rect.right, rect.bottom],
                            }
                        )
                    for child in ctrl.children():
                        traverse(child, depth + 1)
                except Exception:
                    pass

            traverse(front_window)
            return elements
        except Exception:
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
        pyautogui.dragTo(dest_x, dest_y, duration=0.5, button="left")

    def type_via_clipboard(self, text: str):
        saved = pyperclip.paste()
        try:
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        finally:
            if isinstance(saved, str):
                pyperclip.copy(saved)

    def press_hotkey(self, keys: str):
        pyautogui.hotkey(
            *[p if p != "control" else "ctrl" for p in keys.lower().split("+")]
        )

    def hide_other_apps(self, keep_apps: list) -> list:
        try:
            import win32gui
            import win32con

            hidden_apps = []
            hwnd_front = win32gui.GetForegroundWindow()

            def enum_handlers(hwnd, lParam):
                if win32gui.IsWindowVisible(hwnd) and hwnd != hwnd_front:
                    title = win32gui.GetWindowText(hwnd)
                    if title and title not in keep_apps:
                        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                        hidden_apps.append(title)
                return True

            win32gui.EnumWindows(enum_handlers, None)
            return hidden_apps
        except Exception:
            return []

    def launch_app(self, target_path: str) -> None:
        import os
        os.startfile(target_path)

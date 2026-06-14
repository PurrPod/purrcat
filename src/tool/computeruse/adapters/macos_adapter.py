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

    def get_focused_element_info(self) -> str:
        """获取当前获取焦点的元素，避免盲目猜测"""
        try:
            import AppKit
            from ApplicationServices import AXUIElementCreateSystemWide, AXUIElementCopyAttributeValue

            workspace = AppKit.NSWorkspace.sharedWorkspace()
            active_app = workspace.frontmostApplication()
            app_name = active_app.localizedName() if active_app else "未知应用"

            system_wide = AXUIElementCreateSystemWide()
            err, focused_element = AXUIElementCopyAttributeValue(system_wide, "AXFocusedUIElement", None)

            if err == 0 and focused_element:
                _, role = AXUIElementCopyAttributeValue(focused_element, "AXRole", None)
                _, title = AXUIElementCopyAttributeValue(focused_element, "AXTitle", None)
                _, val = AXUIElementCopyAttributeValue(focused_element, "AXValue", None)

                role_str = role.replace('AX', '') if role else "Element"
                desc = title or val or ""
                if desc:
                    return f"焦点位于: [{role_str}] '{desc}' (所属应用: {app_name})"
                return f"焦点位于: [{role_str}] (所属应用: {app_name})"

            return f"当前活动应用: {app_name}"
        except Exception:
            return ""

    def get_ui_tree_elements(self) -> list:
        """限制深度的原生 UI 树解析，解决空白输入框致盲问题"""
        elements = []
        try:
            import AppKit
            from ApplicationServices import AXUIElementCreateApplication, AXUIElementCopyAttributeValue

            workspace = AppKit.NSWorkspace.sharedWorkspace()
            active_app = workspace.frontmostApplication()
            if not active_app:
                return []

            app_element = AXUIElementCreateApplication(active_app.processIdentifier())

            err, focused_window = AXUIElementCopyAttributeValue(app_element, "AXFocusedWindow", None)
            if err != 0 or not focused_window:
                err, focused_window = AXUIElementCopyAttributeValue(app_element, "AXMainWindow", None)
                if err != 0 or not focused_window:
                    return []

            VALID_ROLES = ["AXButton", "AXTextField", "AXTextArea", "AXLink", "AXMenuItem", "AXStaticText", "AXCheckBox"]

            def traverse(element, depth=0):
                if depth > 5:
                    return  # 严格限制深度防卡死

                err_role, role = AXUIElementCopyAttributeValue(element, "AXRole", None)
                if err_role == 0 and role in VALID_ROLES:
                    _, title = AXUIElementCopyAttributeValue(element, "AXTitle", None)
                    _, val = AXUIElementCopyAttributeValue(element, "AXValue", None)
                    _, help_text = AXUIElementCopyAttributeValue(element, "AXHelp", None)
                    _, desc = AXUIElementCopyAttributeValue(element, "AXDescription", None)

                    # 提取占位符(Placeholder)和气泡提示(ToolTip)
                    text = title or val or help_text or desc or ""

                    try:
                        err_pos, pos_val = AXUIElementCopyAttributeValue(element, "AXPosition", None)
                        err_size, size_val = AXUIElementCopyAttributeValue(element, "AXSize", None)

                        if err_pos == 0 and err_size == 0 and pos_val and size_val:
                            x, y = pos_val.x, pos_val.y
                            w, h = size_val.width, size_val.height

                            elements.append({
                                "type": f"[{role.replace('AX', '')}]",
                                "text": str(text),
                                "bbox": [x, y, x + w, y + h]
                            })
                    except:
                        pass

                err_children, children = AXUIElementCopyAttributeValue(element, "AXChildren", None)
                if err_children == 0 and children:
                    for child in children:
                        traverse(child, depth + 1)

            traverse(focused_window)
        except Exception:
            pass
        return elements

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
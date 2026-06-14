from abc import ABC, abstractmethod
from typing import Tuple, List, Dict
from PIL import Image


class BasePlatformAdapter(ABC):
    @abstractmethod
    def get_screen_size(self) -> Tuple[int, int]:
        pass

    @abstractmethod
    def get_screenshot_image(self) -> Image.Image:
        pass

    @abstractmethod
    def get_ocr_elements(self, img_array) -> List[Dict]:
        pass

    @abstractmethod
    def get_ui_tree_elements(self) -> List[Dict]:
        pass

    @abstractmethod
    def get_focused_element_info(self) -> str:
        """获取当前拥有焦点的控件信息或活动窗口标题"""
        pass

    @abstractmethod
    def move_mouse(self, x: int, y: int) -> None:
        pass

    @abstractmethod
    def click(self, x: int, y: int, button: str, clicks: int) -> None:
        pass

    @abstractmethod
    def drag_mouse(self, dest_x: int, dest_y: int) -> None:
        pass

    @abstractmethod
    def scroll(self, amount: int) -> None:
        pass

    @abstractmethod
    def type_via_clipboard(self, text: str) -> None:
        pass

    @abstractmethod
    def press_hotkey(self, keys: str) -> None:
        pass

    @abstractmethod
    def hide_other_apps(self, keep_apps: List[str]) -> List[str]:
        pass
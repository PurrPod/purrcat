from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseSensor(ABC):
    def __init__(self, channel_name: str):
        self.channel_name = channel_name

    @abstractmethod
    def observe(self, *args, **kwargs) -> Optional[Any]:
        pass

    @abstractmethod
    def express(self, message: Any, target_id: Optional[str] = None, **kwargs) -> bool:
        pass
from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseSensor(ABC):
    config_key: str = ""

    def __init__(self, sensor_type: str, sensor_name: str, config_dict: dict):
        self.sensor_type = sensor_type
        self.sensor_name = sensor_name
        self.config_dict = config_dict

    @property
    def is_enabled(self) -> bool:
        return self.config_dict.get("enabled", False)

    def observe(self, *args, **kwargs) -> Optional[Any]:
        if not self.is_enabled:
            return None
        return self._observe(*args, **kwargs)

    @abstractmethod
    def _observe(self, *args, **kwargs) -> Optional[Any]:
        pass

    def express(self, message: Any, **kwargs) -> bool:
        if not self.is_enabled:
            return False
        return self._express(message, **kwargs)

    @abstractmethod
    def _express(self, message: Any, **kwargs) -> bool:
        pass
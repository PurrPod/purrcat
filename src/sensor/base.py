from abc import ABC, abstractmethod
from typing import Any, Optional

from src.utils.config import get_sensor_config


class BaseSensor(ABC):
    def __init__(self, sensor_type: str, sensor_name: str):
        self.sensor_type = sensor_type
        self.sensor_name = sensor_name

    @property
    def is_enabled(self) -> bool:
        config = get_sensor_config().get(self.sensor_name, {})
        return config.get("enabled", False)

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
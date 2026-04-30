import collections
from typing import Any, Optional

from src.sensor.base import BaseSensor


class SensorGateway:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.sensors: dict[str, BaseSensor] = {}
        self.active_channels = collections.deque()

    def register(self, sensor: BaseSensor) -> None:
        self.sensors[sensor.channel_name] = sensor

    def push_active_channel(self, channel_name: str, session_id: Optional[str] = None) -> None:
        self.active_channels.append({"channel": channel_name, "session_id": session_id})

    def pop_active_channel(self) -> Optional[dict]:
        if self.active_channels:
            return self.active_channels.popleft()
        return None

    def express(self, message: Any, fallback_channel: str = "feishu", **kwargs) -> bool:
        active = self.pop_active_channel()
        channel_name = active["channel"] if active else fallback_channel
        sensor = self.sensors.get(channel_name)
        if not sensor:
            raise ValueError(f"未找到对应的 Sensor 实例: {channel_name}")
        return sensor.express(message, target_id=active.get("session_id") if active else None, **kwargs)

    def get_sensor(self, channel_name: str) -> Optional[BaseSensor]:
        return self.sensors.get(channel_name)


_gateway = SensorGateway()


def get_gateway() -> SensorGateway:
    return _gateway
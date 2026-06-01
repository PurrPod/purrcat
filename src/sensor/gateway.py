import json
import sys
from typing import Any, Optional


class RemoteSensorProxy:
    def __init__(self, name: str, capabilities: dict, stdin_pipe):
        self.name = name
        self.can_observe = capabilities.get("observe", False)
        self.can_express = capabilities.get("express", False)
        self.stdin_pipe = stdin_pipe

    def express(self, message: Any, **kwargs) -> bool:
        if not self.can_express:
            return False

        payload = {
            "method": "express",
            "params": {
                "message": str(message),
                "kwargs": kwargs
            }
        }
        try:
            self.stdin_pipe.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.stdin_pipe.flush()
            return True
        except Exception as e:
            print(f"❌ [Gateway] 向 {self.name} 发送数据失败: {e}")
            return False


class SensorGateway:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.sensors: dict[str, RemoteSensorProxy] = {}
        self.active_channels = set()

    def register(self, proxy: RemoteSensorProxy) -> None:
        self.sensors[proxy.name] = proxy

    def push(self, sensor_name: str, content: str) -> None:
        if isinstance(content, str) and content.strip() == "/unbind":
            if sensor_name in self.active_channels:
                self.active_channels.remove(sensor_name)
                self.sensors[sensor_name].express("✅ 已解除活跃状态，可通过再次发送消息保持活跃")
            return

        proxy = self.sensors.get(sensor_name)
        if not proxy:
            return

        if proxy.can_express and sensor_name not in self.active_channels:
            self.active_channels.add(sensor_name)
            proxy.express("✅ 已标记当前会话为活跃窗口\n输入`/unbind`解除绑定")

        print(f"\n📥 [Sensor Input | {sensor_name}] -> {content}")

        try:
            from src.agent import agent_force_push
            agent_force_push(content=content, type=sensor_name)
        except Exception as e:
            print(f"❌ [Gateway] 无法推送消息给 Agent: {e}")

    def send(self, message: Any, **kwargs) -> bool:
        success_count = 0
        for channel_name in list(self.active_channels):
            proxy = self.sensors.get(channel_name)
            if proxy and proxy.express(message, **kwargs):
                success_count += 1
        return success_count > 0


_gateway = SensorGateway()


def get_gateway() -> SensorGateway:
    return _gateway
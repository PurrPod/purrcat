import collections
import json
from typing import Any, Optional
from src.sensor.base import BaseSensor
from src.agent.manager import get_agent

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
        self.sensors: dict[str, BaseSensor] = {}
        self.message_queue = collections.deque()
        self.active_channels = set()

    def register(self, sensor: BaseSensor) -> None:
        self.sensors[sensor.sensor_name] = sensor

    def push(self, sensor: BaseSensor, content: Any) -> None:
        # 1. 拦截并处理解绑逻辑
        if isinstance(content, str) and content.strip() == "/unbind":
            if sensor.sensor_name in self.active_channels:
                self.active_channels.remove(sensor.sensor_name)
                # 解绑成功，调用该 sensor 的 express 回传提示信息
                sensor.express("已解除活跃状态，可通过再次发送消息保持活跃")
            return

        # 2. 正常消息打包
        message_dict = {
            "type": "sensor_input",
            "sensor_type": sensor.sensor_type,
            "sensor_name": sensor.sensor_name,
            "content": content
        }
        self.message_queue.append(message_dict)

        # 3. 处理 message 类型的活跃状态绑定
        if sensor.sensor_type == "message":
            # 判断是否是新加入活跃队列（避免每说一句话都提示一次）
            if sensor.sensor_name not in self.active_channels:
                self.active_channels.add(sensor.sensor_name)
                # 新标记为活跃时，回传提示信息
                sensor.express("已标记当前会话为活跃窗口，输入/unbind解除活跃状态")

        # 4. 推送给前台 Agent
        agent = get_agent()
        if agent:
            payload = json.dumps(message_dict, ensure_ascii=False)
            agent.force_push(payload, type=sensor.sensor_type)

    def send(self, message: Any, **kwargs) -> bool:
        success_count = 0
        for channel_name in list(self.active_channels):
            sensor = self.sensors.get(channel_name)
            if sensor:
                if sensor.express(message, **kwargs):
                    success_count += 1
        return success_count > 0

    def get_sensor(self, sensor_name: str) -> Optional[BaseSensor]:
        return self.sensors.get(sensor_name)

_gateway = SensorGateway()

def get_gateway() -> SensorGateway:
    return _gateway
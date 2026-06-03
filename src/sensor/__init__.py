from .manager import get_manager
from .gateway import get_gateway


def auto_discover_and_start():
    print("🔍 [SensorManager] 开始解析配置并启动 Sensor 服务...")
    get_manager().load_and_start_all()


def send_to_sensors(message: str, **kwargs) -> bool:
    gateway = get_gateway()
    return gateway.send(message, **kwargs)


__all__ = ["auto_discover_and_start", "send_to_sensors"]

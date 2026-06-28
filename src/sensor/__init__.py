from .manager import get_manager
from .gateway import get_gateway
from src.tool.loop.loop_manager import get_loop_manager


def auto_discover_and_start():
    print("🔍 [SensorManager] 开始解析配置并启动 Sensor 服务...")
    get_manager().load_and_start_all()
    
    print("🔄 [LoopManager] 正在装载全局后台动态循环驱动链...")
    get_loop_manager().start()


def send_to_sensors(message: str, **kwargs) -> bool:
    gateway = get_gateway()
    return gateway.send(message, **kwargs)


__all__ = ["auto_discover_and_start", "send_to_sensors"]
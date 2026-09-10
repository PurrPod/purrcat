from .manager import get_manager


def auto_discover_and_start():
    print("🔍 [SensorManager] 开始解析配置并启动 Sensor 服务...")
    get_manager().load_and_start_all()


__all__ = ["auto_discover_and_start"]

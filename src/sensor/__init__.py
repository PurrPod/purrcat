"""
传感器网关与插件自动发现
"""
import importlib
import pkgutil


def auto_discover_and_start():
    print("🔍 [Plugin Loader] 开始全盘扫描 Sensor 插件...")
    import src.sensor
    from src.utils.config import get_sensor_config

    for _, module_name, is_pkg in pkgutil.walk_packages(
        src.sensor.__path__, src.sensor.__name__ + "."
    ):
        try:
            importlib.import_module(module_name)
        except Exception as e:
            print(f"⚠️ [Plugin Loader] 模块 {module_name} 解析异常，已跳过: {e}")

    full_config = get_sensor_config()

    from src.sensor.base import BaseSensor
    from src.sensor.gateway import get_gateway

    def get_all_subclasses(cls):
        all_subclasses = set(cls.__subclasses__())
        for subclass in cls.__subclasses__():
            all_subclasses.update(get_all_subclasses(subclass))
        return list(all_subclasses)

    gateway = get_gateway()
    loaded_count = 0

    for cls in get_all_subclasses(BaseSensor):
        config_key = getattr(cls, "config_key", None)
        if not config_key:
            continue

        cfg = full_config.get(config_key, {})
        if cfg.get("enabled", False):
            try:
                instance = cls(config_dict=cfg)
                gateway.register(instance)
                instance.observe()
                loaded_count += 1
                print(
                    f"✅ [Plugin Loader] 成功装载并启动: {cls.__name__} (键: {config_key})"
                )
            except Exception as e:
                print(f"❌ [Plugin Loader] 插件 {cls.__name__} 启动崩溃: {e}")

    print(f"🚀 [Plugin Loader] 扫描结束，共启动 {loaded_count} 个 Sensor 插件。")


def send_to_sensors(message: str, **kwargs) -> bool:
    """将消息广播给当前活跃的传感器通道。"""
    from src.sensor.gateway import get_gateway

    gateway = get_gateway()
    return gateway.send(message, **kwargs)


def get_registered_sensor_names() -> list[str]:
    """返回当前已注册传感器名称列表。"""
    from src.sensor.gateway import get_gateway

    gateway = get_gateway()
    return list(gateway.sensors.keys())


__all__ = ["auto_discover_and_start", "send_to_sensors", "get_registered_sensor_names"]

import threading


class SingletonMeta(type):
    """
    线程安全的单例元类
    修复版：为每个类分配独立的互斥锁，彻底解决嵌套单例死锁和高并发竞争问题
    """

    _instances = {}
    _locks = {}
    _global_lock = threading.Lock()  # 仅用于保护 _locks 字典的初始化

    def __call__(cls, *args, **kwargs):
        # 1. 安全地获取或创建针对当前类的专属锁
        if cls not in cls._locks:
            with cls._global_lock:
                if cls not in cls._locks:
                    cls._locks[cls] = (
                        threading.RLock()
                    )  # 使用 RLock 支持类的自我嵌套调用

        # 2. 使用专属锁进行单例实例化
        with cls._locks[cls]:
            if cls not in cls._instances:
                cls._instances[cls] = super().__call__(*args, **kwargs)

        return cls._instances[cls]

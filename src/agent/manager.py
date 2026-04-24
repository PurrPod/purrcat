# src/agent/manager.py
import threading
from src.agent.agent import Agent
from src.utils.config import CHECKPOINT_PATH


class AgentManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AgentManager, cls).__new__(cls)
                cls._instance._agent = None
                cls._instance._sensor_thread = None
        return cls._instance

    def init_agent(self, name=None, checkpoint_path=CHECKPOINT_PATH):
        """初始化 Agent 并启动后台监听线程"""
        if self._agent is not None:
            print("⚠️ Agent 已经初始化过了")
            return self._agent

        print("🚀 正在初始化全局 Agent...")
        # 从检查点恢复或新建 Agent
        self._agent = Agent.load_checkpoint(filepath=checkpoint_path, name=name)

        # 将 sensor 挂载到后台守护线程，防止阻塞主进程
        self._sensor_thread = threading.Thread(
            target=self._agent.sensor,
            daemon=True,
            name="AgentSensorThread"
        )
        self._sensor_thread.start()
        print("✅ Agent 后台心跳已启动")
        return self._agent

    def get_agent(self) -> Agent:
        """获取全局 Agent 实例"""
        if self._agent is None:
            raise RuntimeError("Agent 尚未初始化，请先调用 init_agent()")
        return self._agent

    def force_push(self, content: str, source: str = None):
        """全局便捷入口：强制推送消息"""
        if self._agent is None:
            print("⚠️ Agent 未初始化，无法推送消息")
            return
        self._agent.force_push(content, source)

    def shutdown(self):
        """优雅关闭 Agent"""
        if self._agent:
            print("🛑 正在关闭 Agent 并保存现场...")
            self._agent.stop() # 通知 sensor 停止循环

        # 稍微等一下子线程，最多等3秒
        if self._sensor_thread and self._sensor_thread.is_alive():
            self._sensor_thread.join(timeout=3.0)
            print("✅ Agent 线程已安全终止")
            
        # 最后必须执行一次落盘，保存（比如撤销了一半的）最终状态
        if self._agent:
            self._agent.save_checkpoint()
        print("✅ Agent 已安全终止")


# 提供全局便捷方法
manager = AgentManager()
init_agent = manager.init_agent
get_agent = manager.get_agent
force_push = manager.force_push
shutdown_agent = manager.shutdown
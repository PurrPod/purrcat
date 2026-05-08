# src/agent/manager.py
import threading
from src.agent.agent import Agent
from src.agent.session_store import SessionStore


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

    def init_agent(self, name=None, session_id=None):
        if self._agent is not None:
            return self._agent

        print("🚀 正在初始化全局 Agent...")
        
        if not session_id:
            all_sessions = SessionStore.get_all_sessions()
            if all_sessions:
                session_id = max(all_sessions.keys(), key=lambda k: all_sessions[k].get("updated_at", ""))
            else:
                session_id = SessionStore._generate_id()
                
        history = SessionStore.load_session_history(session_id)
        
        if history and history[-1].get("role") == "assistant" and history[-1].get("tool_calls"):
            print("🛠️ [Checkpoint] 撤销最近一次未完成的工具调用...")
            history.pop()

        self._agent = Agent(session_id=session_id, initial_history=history, name=name, save_callback=self.notify_save)
        
        self._sensor_thread = threading.Thread(
            target=self._agent.sensor,
            daemon=True,
            name="AgentSensorThread"
        )
        self._sensor_thread.start()
        print(f"✅ Agent 已启动，当前挂载会话: {session_id}")
        return self._agent

    def get_agent(self) -> Agent:
        if self._agent is None:
            raise RuntimeError("Agent 尚未初始化")
        return self._agent

    def notify_save(self):
        """Agent 上下文发生变化时，被 Agent 回调落盘"""
        if self._agent:
            SessionStore.save_session(self._agent.session_id, self._agent.current_history)

    def list_sessions(self):
        """返回索引树给前端渲染"""
        return SessionStore.get_all_sessions()

    def branch_current_session(self, branch_alias=None):
        """拉取新分支并自动切换"""
        if not self._agent:
            return None
            
        with self._agent._lock:
            self.notify_save()
            
            new_id = SessionStore.create_branch(
                current_session_id=self._agent.session_id,
                current_history=self._agent.current_history,
                branch_alias=branch_alias
            )
            
            self._agent.session_id = new_id
            self._agent.window_token = 0 
            self._agent.model.bind_task(new_id, "AgentMain")
            
            print(f"🌿 成功拉取新分支并检出: {new_id} ({branch_alias})")
            return new_id

    def checkout_session(self, target_session_id):
        """在历史会话之间无缝切换"""
        if not self._agent:
            return False
            
        with self._agent._lock:
            self.notify_save()
            
            new_history = SessionStore.load_session_history(target_session_id)
            
            self._agent.session_id = target_session_id
            self._agent.current_history = new_history
            
            if not self._agent.current_history:
                self._agent.current_history = [{"role": "system", "content": self._agent.system_prompt}]
            elif self._agent.current_history[0].get("role") == "system":
                self._agent.current_history[0]["content"] = self._agent.system_prompt
                
            self._agent.window_token = 0
            self._agent.model.bind_task(target_session_id, "AgentMain")
            
            print(f"🔄 检出成功: {target_session_id}")
            return True

    def shutdown(self):
        if self._agent:
            self._agent.stop()
            self.notify_save()
        if self._sensor_thread and self._sensor_thread.is_alive():
            self._sensor_thread.join(timeout=3.0)


manager = AgentManager()
init_agent = manager.init_agent
get_agent = manager.get_agent
shutdown_agent = manager.shutdown
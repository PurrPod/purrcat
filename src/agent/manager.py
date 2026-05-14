import threading
import time
import json
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
            session_id = max(all_sessions.keys(), key=lambda k: all_sessions[k].get("updated_at",
                                                                                    "")) if all_sessions else SessionStore._generate_id()

        history = SessionStore.load_session_history(session_id)
        if history and history[-1].get("role") == "assistant" and history[-1].get("tool_calls"):
            history.pop()

        self._agent = Agent(session_id=session_id, initial_history=history, name=name, save_callback=self.notify_save)

        self._sensor_thread = threading.Thread(target=self._agent.sensor, daemon=True, name="AgentSensorThread")
        self._sensor_thread.start()

        self.notify_save()

        print(f"✅ Agent 已启动，当前挂载会话: {session_id}")
        return self._agent

    def get_agent(self) -> Agent:
        if self._agent is None:
            raise RuntimeError("Agent 尚未初始化")
        return self._agent

    def notify_save(self):
        if self._agent:
            safe_history = self._agent.get_history()
            SessionStore.save_session(self._agent.session_id, safe_history)

    def list_sessions(self):
        return SessionStore.get_all_sessions()

    def branch_current_session(self, branch_alias=None):
        if not self._agent: return None

        wait_count = 0
        while self._agent.state != "idle" and wait_count < 6:
            print("⏳ 正在等待 Agent 完成当前回复...")
            time.sleep(0.5)
            wait_count += 1

        if self._agent.state != "idle":
            print("⚠️ Agent 忙碌超时，强制打断执行分支拉取！")
            self._agent.force_interrupt()

        self.notify_save()
        safe_history = self._agent.get_history()

        new_id = SessionStore.create_branch(
            current_session_id=self._agent.session_id,
            current_history=safe_history,
            branch_alias=branch_alias
        )

        new_history = SessionStore.load_session_history(new_id)

        with self._agent._history_lock:
            self._agent.session_id = new_id
            self._agent.window_token = 0
            self._agent.current_history = new_history

        self._agent.model.bind_task(new_id, "AgentMain")
        print(f"🌿 成功拉取新分支并检出: {new_id} ({branch_alias})")
        return new_id

    def create_clean_session(self, branch_alias=None):
        if not self._agent: return None

        wait_count = 0
        while self._agent.state != "idle" and wait_count < 6:
            print("⏳ 正在等待 Agent 完成当前回复...")
            time.sleep(0.5)
            wait_count += 1

        if self._agent.state != "idle":
            print("⚠️ Agent 忙碌超时，强制打断执行纯净分支创建！")
            self._agent.force_interrupt()

        self.notify_save()

        # 【重点】创建全新分支，现场获取最新全局规则，开辟新的 KV Cache 路线
        fresh_prompt = self._agent._build_system_prompt()
        new_id = SessionStore._generate_id()
        clean_history = [{"role": "system", "content": fresh_prompt}]

        # 挂载共享的短时缓存（作为独立的系统消息，不污染首条 KV Cache）
        if hasattr(self._agent, 'memo') and self._agent.memo:
            memo_summary = json.dumps(self._agent.memo, ensure_ascii=False, indent=2)
            clean_history.append({
                "role": "system",
                "content": f"【系统通知：这是一个全新的会话。以下是你最近的短时工作缓存，请利用这些缓存无缝接续当前工作：】\n{memo_summary}"
            })

        SessionStore.save_session(
            session_id=new_id,
            history=clean_history,
            parent_id=None,
            alias=branch_alias
        )

        with self._agent._history_lock:
            self._agent.session_id = new_id
            self._agent.window_token = 0
            self._agent.current_history = clean_history

        self._agent.model.bind_task(new_id, "AgentMain")
        print(f"✨ 成功创建纯净新分支并检出: {new_id} ({branch_alias})")
        return new_id

    def checkout_session(self, target_session_id):
        if not self._agent: return False

        wait_count = 0
        while self._agent.state != "idle" and wait_count < 6:
            print("⏳ 正在等待 Agent 释放资源...")
            time.sleep(0.5)
            wait_count += 1

        if self._agent.state != "idle":
            print("⚠️ 强制打断，执行会话切换！")
            self._agent.force_interrupt()

        self.notify_save()
        new_history = SessionStore.load_session_history(target_session_id)

        with self._agent._history_lock:
            self._agent.session_id = target_session_id
            self._agent.current_history = new_history
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
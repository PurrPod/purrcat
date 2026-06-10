import json
import os
import threading
import time

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

    # ==========================================
    # 1. 生命周期管理 (Lifecycle)
    # ==========================================
    def init_agent(self, name=None, session_id=None):
        if self._agent is not None:
            return self._agent.session_id

        print("🚀 正在初始化全局 Agent...")
        all_sessions = SessionStore.get_all_sessions()

        if not session_id:
            session_id = (
                max(
                    all_sessions.keys(),
                    key=lambda k: str(all_sessions[k].get("updated_at") or ""),
                )
                if all_sessions
                else SessionStore._generate_id()
            )

        history = SessionStore.load_session_history(session_id)
        if (
            history
            and history[-1].get("role") == "assistant"
            and history[-1].get("tool_calls")
        ):
            history.pop()

        self._agent = Agent(
            session_id=session_id,
            initial_history=history,
            name=name,
            save_callback=self._notify_save,
        )

        # 恢复 Token 进度
        if session_id in all_sessions:
            self._agent.window_token = all_sessions[session_id].get("window_token", 0)

        self._sensor_thread = threading.Thread(
            target=self._agent.sensor, daemon=True, name="AgentSensorThread"
        )
        self._sensor_thread.start()

        self._notify_save()
        print(f"✅ Agent 已启动，当前挂载会话: {session_id}")
        return session_id

    def shutdown_agent(self):
        if self._agent:
            self._agent.stop()
            self._notify_save()
        if self._sensor_thread and self._sensor_thread.is_alive():
            self._sensor_thread.join(timeout=3.0)

    # ==========================================
    # 2. 交互与通信 (Interaction)
    # ==========================================
    def agent_force_push(self, content: str, type: str = "user"):
        """代替外部直接调用 agent.force_push，实现完美封装"""
        if not self._agent:
            self.init_agent()
        self._agent.force_push(content, type=type)
        return True

    def agent_force_push_batch(self, events: list):
        """批量强制推送消息，避免被 sensor 线程在中间截断"""
        if not self._agent:
            self.init_agent()
        self._agent.force_push_batch(events)
        return True

    # ==========================================
    # 3. 会话控制 (Session Commands)
    # ==========================================
    def switch_session(self, target_session_id: str):
        """原 checkout_session：切换到指定会话"""
        if not self._agent:
            self.init_agent(session_id=target_session_id)
            return True

        # ✨ 新增：如果是当前会话，直接秒回，什么都不做
        if self._agent.session_id == target_session_id:
            return True

        if self._agent.state != "idle":
            print("⏳ 正在阻塞等待 Agent 释放资源，以安全检出目标会话...")
            while self._agent.state != "idle":
                time.sleep(0.5)

        self._notify_save()
        new_history = SessionStore.load_session_history(target_session_id)
        all_sessions = SessionStore.get_all_sessions()

        with self._agent._history_lock:
            self._agent.session_id = target_session_id
            self._agent.current_history = new_history
            self._agent.window_token = all_sessions.get(target_session_id, {}).get(
                "window_token", 0
            )

        self._agent.model.bind_task(target_session_id, "AgentMain")
        print(f"🔄 检出成功: {target_session_id}")
        return True

    def new_session(self, branch_alias=None):
        """原 create_clean_session：开启一个全新的空白会话"""
        if not self._agent:
            self.init_agent()

        if self._agent.state != "idle":
            print("⏳ 正在阻塞等待 Agent 完成当前回复...")
            while self._agent.state != "idle":
                time.sleep(0.5)

        self._notify_save()

        fresh_prompt = self._agent._build_system_prompt()
        new_id = SessionStore._generate_id()
        clean_history = [{"role": "system", "content": fresh_prompt}]

        if hasattr(self._agent, "memo") and self._agent.memo:
            memo_summary = json.dumps(self._agent.memo, ensure_ascii=False, indent=2)
            clean_history.append(
                {
                    "role": "system",
                    "content": f"【系统通知：这是一个全新的会话。以下是共享记忆缓存：】\n{memo_summary}",
                }
            )

        SessionStore.save_session(
            session_id=new_id, history=clean_history, parent_id=None, alias=branch_alias
        )

        with self._agent._history_lock:
            self._agent.session_id = new_id
            self._agent.window_token = 0
            self._agent.current_history = clean_history

        self._agent.model.bind_task(new_id, "AgentMain")
        print(f"✨ 成功创建纯净新分支: {new_id}")
        return new_id

    def branch_session(self, branch_alias=None):
        """原 branch_current_session：基于当前进度衍生新分支"""
        if not self._agent:
            self.init_agent()

        if self._agent.state != "idle":
            print("⏳ 正在阻塞等待 Agent 完成当前回复，以确保安全拉取分支...")
            while self._agent.state != "idle":
                time.sleep(0.5)

        self._notify_save()
        safe_history = self._agent.get_history()
        current_token = self._agent.window_token

        new_id = SessionStore.create_branch(
            current_session_id=self._agent.session_id,
            current_history=safe_history,
            branch_alias=branch_alias,
            window_token=current_token,
        )

        new_history = SessionStore.load_session_history(new_id)

        with self._agent._history_lock:
            self._agent.session_id = new_id
            self._agent.window_token = current_token
            self._agent.current_history = new_history

        self._agent.model.bind_task(new_id, "AgentMain")
        print(f"🌿 成功拉取新分支并检出: {new_id} ({branch_alias})")
        return new_id

    def delete_session(self, session_id: str):
        """新增：安全删除会话（支持新的文件夹结构）"""
        # 1. 拦截正在运行的会话删除
        if self._agent and self._agent.session_id == session_id:
            raise ValueError("不能删除当前正在活跃的会话")

        # 2. 执行删除（删除整个会话文件夹）
        from src.utils.config import SESSIONS_DIR

        session_dir = os.path.join(SESSIONS_DIR, session_id)
        if os.path.exists(session_dir) and os.path.isdir(session_dir):
            import shutil

            shutil.rmtree(session_dir)
            print(f"🗑️ 已删除会话文件夹: {session_dir}")

        # 3. 更新索引文件
        index_file = os.path.join(SESSIONS_DIR, "index.json")
        if os.path.exists(index_file):
            with SessionStore._index_lock:
                try:
                    with open(index_file, "r", encoding="utf-8") as f:
                        idx = json.load(f)
                    if session_id in idx:
                        del idx[session_id]
                        with open(index_file, "w", encoding="utf-8") as f:
                            json.dump(idx, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"Error updating index: {e}")
        return True

    # ==========================================
    # 4. 数据读取 (Queries - 给 API 和前端使用)
    # ==========================================
    def get_chat_history(self, session_id: str = None, branch_id: str = "main"):
        if not self._agent:
            self.init_agent()

        # 如果是当前的活跃会话且查的是 main，优先从内存拿最新状态
        if branch_id == "main" and (
            not session_id or session_id == self._agent.session_id
        ):
            return [m for m in self._agent.get_history() if m.get("role") != "system"]

        # 否则一律透传 branch_id 从磁盘加载特定的隔离子分支历史
        return [
            m
            for m in SessionStore.load_session_history(session_id, branch_id=branch_id)
            if m.get("role") != "system"
        ]

    def get_session_list(self):
        return SessionStore.get_all_sessions()

    def get_active_session_id(self):
        return self._agent.session_id if self._agent else None

    # ==========================================
    # 5. 热重载控制 (Hot Reload)
    # ==========================================
    def reload_model(self):
        """热更新主 Agent 的模型配置"""
        if self._agent:
            print("🔄 检测到模型配置更改，正在热重载主 Agent 模型...")
            from src.model import AgentModel
            from src.utils.config import get_agent_model

            # 1. 释放旧的 API Key 和并发锁资源
            if hasattr(self._agent, "model") and self._agent.model:
                self._agent.model.unbind()

            # 2. 重新初始化 AgentModel（其内部会重新调用 get_model_config() 读盘）
            try:
                self._agent.name = get_agent_model()
                self._agent.model = AgentModel(self._agent.session_id)
                self._agent.model.bind_task(self._agent.session_id, "AgentMain")
                print("✅ 主 Agent 模型配置热重载完成！")
            except Exception as e:
                print(f"❌ 热重载失败，请检查模型配置是否正确: {e}")

    # ==========================================
    # 内部私有方法
    # ==========================================
    def _notify_save(self):
        if self._agent:
            safe_history = self._agent.get_history()
            SessionStore.save_session(
                self._agent.session_id,
                safe_history,
                window_token=self._agent.window_token,
            )


# 全局单例和兼容形式导出
manager = AgentManager()


def get_agent():
    return manager.get_agent()

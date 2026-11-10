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

        print("[Init] 正在初始化全局 Agent...")
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

        # 恢复该会话绑定的范式（未绑定则回落默认 PARADIGM.yaml）
        paradigm_path = None
        stored_paradigm = all_sessions.get(session_id, {}).get("paradigm")
        if stored_paradigm:
            from src.utils.paradigm_api import resolve_paradigm_path

            paradigm_path = resolve_paradigm_path(stored_paradigm)

        self._agent = Agent(
            session_id=session_id,
            initial_history=history,
            name=name,
            save_callback=self._notify_save,
            paradigm_path=paradigm_path,
        )

        # 恢复 Token 进度（权威来源为会话 meta.json，而非不含该字段的 index.json）
        if session_id in all_sessions:
            self._agent.window_token = SessionStore.get_session_window_token(session_id)
            # 恢复本会话累计消耗（主/子分支聚合后取主干值）
            self._agent.consumed_tokens = SessionStore.get_session_consumed_tokens(
                session_id
            )["main"]

        self._sensor_thread = threading.Thread(
            target=self._agent.sensor, daemon=True, name="AgentSensorThread"
        )
        self._sensor_thread.start()

        # 心跳机制与 Agent 本体同生命周期（GOAL.md 定时注入，不依赖传感器）
        from src.agent.heartbeat import get_heartbeat_manager

        get_heartbeat_manager().start()

        self._notify_save()
        print(f"[Success] Agent 已启动，当前挂载会话: {session_id}")
        return session_id

    def shutdown_agent(self):
        if self._agent:
            self._agent.stop()
            self._notify_save()
        if self._sensor_thread and self._sensor_thread.is_alive():
            self._sensor_thread.join(timeout=3.0)

    def get_agent(self):
        """暴露当前挂载的 Agent（未初始化时为 None）。"""
        return self._agent

    # ==========================================
    # 1.1 会话切换的内部原子操作
    # ==========================================
    def _wait_until_idle(self, message: str) -> None:
        """阻塞等待 Agent 释放资源，确保会话/分支切换安全。"""
        if self._agent.state != "idle":
            print(message)
            while self._agent.state != "idle":
                time.sleep(0.5)

    def _adopt_session(
        self,
        session_id: str,
        history: list,
        window_token: int,
        consumed_tokens: int,
    ) -> None:
        """在历史锁内一次性切换当前会话的上下文与配额。"""
        with self._agent._history_lock:
            self._agent.session_id = session_id
            self._agent.current_history = history
            self._agent.window_token = window_token
            self._agent.consumed_tokens = consumed_tokens

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

    def agent_force_interrupt(self):
        """🌟 人类强制打断：掐断正在执行的工具（子进程物理 terminate）并隔离旧响应"""
        if not self._agent:
            return False
        self._agent.force_interrupt()
        return True

    # ==========================================
    # 3. 会话控制 (Session Commands)
    # ==========================================
    def switch_session(self, target_session_id: str):
        """原 checkout_session：切换到指定会话"""
        if not self._agent:
            self.init_agent(session_id=target_session_id)
            return True

        # [Create] 新增：如果是当前会话，直接秒回，什么都不做
        if self._agent.session_id == target_session_id:
            return True

        self._wait_until_idle(
            "[Wait] 正在阻塞等待 Agent 释放资源，以安全检出目标会话..."
        )

        self._notify_save()

        new_history = SessionStore.load_session_history(target_session_id)
        all_sessions = SessionStore.get_all_sessions()

        self._adopt_session(
            target_session_id,
            new_history,
            SessionStore.get_session_window_token(target_session_id),
            SessionStore.get_session_consumed_tokens(target_session_id)["main"],
        )

        # 载入该会话绑定的范式（未绑定则回落默认 PARADIGM.yaml）
        from src.utils.paradigm_api import resolve_paradigm_path

        stored_paradigm = all_sessions.get(target_session_id, {}).get("paradigm")
        self._agent.hook_handler.load_config(resolve_paradigm_path(stored_paradigm))

        self._agent.model.bind_task(target_session_id, "AgentMain")
        print(f"[Switch] 检出成功: {target_session_id}")
        return True

    def new_session(self, branch_alias=None, paradigm=None, project_id=None):
        """原 create_clean_session：开启一个全新的空白会话（可指定范式与所属项目）。

        project_id 非空时，把该项目的 MEMORY.md 路径与维护约定追加进系统提示词——只在此刻（项目内
        新建会话）注入一次；把旧会话拖进项目不会改动其既有系统提示。
        """
        if not self._agent:
            self.init_agent()

        self._wait_until_idle("[Wait] 正在阻塞等待 Agent 完成当前回复...")

        self._notify_save()

        from src.utils.paradigm_api import resolve_paradigm_path

        paradigm_path = resolve_paradigm_path(paradigm)

        from src.agent.agent import Agent as TempAgent

        temp_agent = TempAgent(
            session_id=SessionStore._generate_id(),
            initial_history=[],
            paradigm_path=paradigm_path,
        )
        fresh_prompt = temp_agent._build_system_prompt()

        if project_id:
            from src.agent.project_store import ProjectStore

            block = ProjectStore.prompt_block(project_id)
            if block:
                fresh_prompt = f"{fresh_prompt}\n\n---\n\n{block}"

        new_id = SessionStore._generate_id()
        clean_history = [{"role": "system", "content": fresh_prompt}]

        SessionStore.save_session(
            session_id=new_id,
            history=clean_history,
            parent_id=None,
            alias=branch_alias,
            paradigm=paradigm,
            project_id=project_id or None,
        )

        self._adopt_session(new_id, clean_history, 0, 0)

        # 新会话立刻按所选范式工作（未选则默认 PARADIGM.yaml）
        self._agent.hook_handler.load_config(paradigm_path)

        self._agent.model.bind_task(new_id, "AgentMain")
        print(f"[Create] 成功创建纯净新分支: {new_id}")
        return new_id

    def switch_paradigm(self, session_id, paradigm=None):
        """会话暂停时热切换 Agent Loop：只替换 Hook 循环逻辑，绝不重建系统提示词（保住 KV Cache）。"""
        if not self._agent:
            self.init_agent(session_id=session_id)

        if self._agent.session_id != session_id:
            raise ValueError("只能切换当前活跃会话的范式")
        if self._agent.state != "idle":
            raise ValueError("Agent 正在忙，请稍后再切换范式")

        from src.utils.paradigm_api import resolve_paradigm_path

        path = resolve_paradigm_path(paradigm)
        self._agent.hook_handler.load_config(path)  # 仅热替换 hooks/循环配置

        SessionStore.set_session_paradigm(
            session_id,
            paradigm.strip()
            if isinstance(paradigm, str) and paradigm.strip()
            else None,
        )
        print(f"[Paradigm] 会话 {session_id} 已切换范式: {path}")
        return path

    def branch_session(self, branch_alias=None):
        """原 branch_current_session：基于当前进度衍生新分支"""
        if not self._agent:
            self.init_agent()

        self._wait_until_idle(
            "[Wait] 正在阻塞等待 Agent 完成当前回复，以确保安全拉取分支..."
        )

        self._notify_save()
        safe_history = self._agent.get_history()
        current_token = self._agent.window_token
        current_consumed = self._agent.consumed_tokens

        # 分支继承当前会话绑定的范式（仅在非默认范式时记录）
        inherit_paradigm = None
        current_path = getattr(
            getattr(self._agent, "hook_handler", None), "paradigm_path", None
        )
        if current_path:
            base = os.path.splitext(os.path.basename(current_path))[0]
            if base and base.lower() != "paradigm":
                inherit_paradigm = base

        # 分支留在源会话所属项目（系统提示已随历史一并继承，不再重复注入 MEMORY.md）
        source_project = SessionStore.get_session_project(self._agent.session_id)

        # 未显式命名时，分支沿用源会话在列表里的名字并追加「（分支）」
        if not branch_alias:
            source_alias = (
                SessionStore.get_all_sessions()
                .get(self._agent.session_id, {})
                .get("alias")
            )
            branch_alias = f"{source_alias or self._agent.session_id}（分支）"

        new_id = SessionStore.create_branch(
            current_session_id=self._agent.session_id,
            current_history=safe_history,
            branch_alias=branch_alias,
            paradigm=inherit_paradigm,
            window_token=current_token,
            consumed_tokens=current_consumed,
            project_id=source_project,
        )

        new_history = SessionStore.load_session_history(new_id)

        self._adopt_session(new_id, new_history, current_token, current_consumed)

        self._agent.model.bind_task(new_id, "AgentMain")
        print(f"[Branch] 成功拉取新分支并检出: {new_id} ({branch_alias})")
        return new_id

    def delete_session(self, session_id: str):
        """新增：安全删除会话（支持新的文件夹结构）"""
        # 1. 拦截正在运行的会话删除
        if self._agent and self._agent.session_id == session_id:
            raise ValueError("不能删除当前正在活跃的会话")

        # 2. 删除会话文件夹并同步索引
        SessionStore.delete_session(session_id)
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
            print("[Switch] 检测到模型配置更改，正在热重载主 Agent 模型...")
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
                print("[Success] 主 Agent 模型配置热重载完成！")
            except Exception as e:
                print(f"[Error] 热重载失败，请检查模型配置是否正确: {e}")

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
                consumed_tokens=self._agent.consumed_tokens,
            )


# 全局单例和兼容形式导出
manager = AgentManager()


def get_agent():
    return manager.get_agent()

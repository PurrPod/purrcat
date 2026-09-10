"""
ACP 会话映射 (server/acp/sessions.py)

ACP sessionId（编辑器/sensor 侧的会话标识）↔ purrcat session（内部 AgentManager 会话）。
v1 串行模型：每个 ACP session 绑定一个 purrcat session；prompt 前排队等待
Agent idle 再切换（复用 chat.py 的既有语义）。

watchdog 重启场景：sensor 重新 initialize 时按 client 名清掉 stale 映射。
"""

import threading
import time
import uuid


class AcpSessionRegistry:
    def __init__(self):
        self._lock = threading.RLock()
        # acp_sid -> {"purr_session_id", "client", "mode", "last_prompt_id", "created"}
        self._sessions = {}

    def create(
        self, client: str = "unknown", alias: str = "ACP Session", follow_active: bool = False
    ) -> dict:
        """新建映射。

        - follow_active=False（编辑器）：内部创建一个全新 purrcat 会话
          （AgentManager 排队等 idle 再 switch）
        - follow_active=True（sensor）：不建 purrcat 会话，prompt 始终注入
          **当前活跃会话**（agent_force_push 直达，无 switch 无排队）；
          事件订阅按"全订阅"生效——单活跃会话模型下全订阅 ≈ 活跃会话
        """
        if follow_active:
            purr_id = None
        else:
            from src.agent import new_session as agent_new_session

            purr_id = agent_new_session(branch_alias=alias)
        acp_id = uuid.uuid4().hex
        entry = {
            "purr_session_id": purr_id,
            "client": client,
            "mode": "",
            "follow": follow_active,
            "last_prompt_id": "",
            "created": time.time(),
        }
        with self._lock:
            self._sessions[acp_id] = entry
        return {"acpSessionId": acp_id, **entry}

    def get(self, acp_sid: str) -> dict | None:
        with self._lock:
            return self._sessions.get(acp_sid)

    def set_mode(self, acp_sid: str, mode_id: str) -> bool:
        with self._lock:
            entry = self._sessions.get(acp_sid)
            if entry is None:
                return False
            entry["mode"] = mode_id
            return True

    def mark_prompt(self, acp_sid: str, prompt_id: str) -> bool:
        with self._lock:
            entry = self._sessions.get(acp_sid)
            if entry is None:
                return False
            entry["last_prompt_id"] = prompt_id
            return True

    def drop_by_client(self, client: str) -> int:
        """watchdog 重启后 sensor 重新 initialize：清掉该 client 的 stale 映射"""
        with self._lock:
            stale = [k for k, v in self._sessions.items() if v["client"] == client]
            for k in stale:
                del self._sessions[k]
            return len(stale)


def ensure_active_and_push(purr_session_id: str, message: str, source: str = "acp"):
    """确保 Agent 活跃会话为目标会话后注入消息（后台线程调用）。

    排队语义与 server/api/chat.py 的 _run_agent_task 一致：等 idle 再 switch，
    绝不打断进行中的轮次。
    """
    from src.agent.manager import AgentManager

    manager = AgentManager()
    if manager._agent is None:
        manager.init_agent()

    if manager._agent.session_id != purr_session_id:
        while manager._agent.state != "idle":
            time.sleep(0.3)
        manager.switch_session(purr_session_id)

    manager.agent_force_push(message, type=source)


def push_by_entry(entry: dict, message: str, source: str = "acp"):
    """按会话映射注入消息（后台线程调用）。

    - follow 模式（sensor）：直达当前活跃会话，不 switch 不排队
    - 映射模式（编辑器）：排队等 idle 再 switch（ensure_active_and_push）
    """
    if entry.get("follow"):
        from src.agent import agent_force_push

        agent_force_push(message, type=source)
        return
    ensure_active_and_push(entry["purr_session_id"], message, source)


_registry = AcpSessionRegistry()


def get_registry() -> AcpSessionRegistry:
    return _registry

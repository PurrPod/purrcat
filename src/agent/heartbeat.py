"""
Agent 心跳机制（原 loop 子系统精简版）

设计要点：
- 仅服务 Agent 本体，不再挂钩 harness 工作流，也不依赖传感器子系统
- 每个心跳周期将 GOAL.md 的内容注入 Agent 会话
- GOAL.md 为空时注入兜底提示语
- 间隔最短 60 秒；只有 Agent 回到 idle 状态才开始重新计时
- 配置持久化于 heartbeat.json，API 直接写文件，管理线程按 mtime 热加载
"""

import json
import os
import threading
import time

from src.utils.config import AGENT_CORE_DIR, GOAL_MD_PATH, HEARTBEAT_FILE

# 最短心跳间隔（秒）
MIN_INTERVAL = 60

# GOAL.md 为空时的兜底注入内容
EMPTY_GOAL_MESSAGE = "当前没有待办事项"


class HeartbeatManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._stop_event = threading.Event()
        self._thread = None
        self._cfg_lock = threading.Lock()
        self._cfg = {"interval": 1800, "active": False}
        self._last_mtime = -1.0

    # ==========================================
    # 生命周期
    # ==========================================
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        os.makedirs(AGENT_CORE_DIR, exist_ok=True)
        self._migrate_todo_to_goal()
        self._ensure_config_file()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="AgentHeartbeatThread"
        )
        self._thread.start()
        print("🟢 [Heartbeat] Agent 心跳线程已就位（GOAL.md 注入驱动）")

    def stop(self):
        self._stop_event.set()

    # ==========================================
    # 配置读写（单一数据源：heartbeat.json 文件）
    # ==========================================
    def _ensure_config_file(self):
        if not os.path.exists(HEARTBEAT_FILE):
            self._write_config({"interval": 1800, "active": False})

    def _write_config(self, cfg: dict):
        tmp = HEARTBEAT_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, HEARTBEAT_FILE)

    def get_config(self) -> dict:
        """读取心跳配置（mtime 变化时重载，供管理线程与 API 共用）"""
        with self._cfg_lock:
            try:
                mtime = os.path.getmtime(HEARTBEAT_FILE)
                if mtime != self._last_mtime:
                    with open(HEARTBEAT_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._cfg = {
                        "interval": max(MIN_INTERVAL, int(data.get("interval", 1800))),
                        "active": bool(data.get("active", False)),
                    }
                    self._last_mtime = mtime
            except (FileNotFoundError, json.JSONDecodeError, ValueError):
                self._cfg = {"interval": 1800, "active": False}
                self._last_mtime = -1.0
            return dict(self._cfg)

    @staticmethod
    def read_goal() -> str:
        try:
            with open(GOAL_MD_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            return ""

    # ==========================================
    # 主循环
    # ==========================================
    def _run(self):
        while not self._stop_event.is_set():
            cfg = self.get_config()
            if not cfg["active"]:
                time.sleep(1)
                continue

            # 1. 等待 Agent 空闲，才启动本轮倒计时
            if not self._wait_idle():
                continue

            # 2. 倒计时（每秒检查停机/关闭信号）
            remaining = cfg["interval"]
            while remaining > 0 and not self._stop_event.is_set():
                if not self.get_config()["active"]:
                    remaining = 0
                    break
                time.sleep(1)
                remaining -= 1
            if self._stop_event.is_set() or not self.get_config()["active"]:
                continue

            # 3. 注入前再次等待空闲（期间用户可能正在对话）
            if not self._wait_idle():
                continue

            # 4. 注入 GOAL.md 内容（空则注入兜底提示）
            self._inject()

    def _wait_idle(self) -> bool:
        """阻塞等待 Agent 回到 idle；返回 False 表示心跳已停用/停机"""
        while not self._stop_event.is_set():
            if not self.get_config()["active"]:
                return False
            try:
                from src.agent.manager import manager as agent_manager

                agent = agent_manager._agent
                if agent is None or agent.state == "idle":
                    return True
            except Exception:
                return True
            time.sleep(0.5)
        return False

    def _inject(self):
        goal = self.read_goal()
        if goal:
            content = f"⏰ [Heartbeat] 当前目标 (GOAL.md)：\n{goal}"
        else:
            content = f"⏰ [Heartbeat] {EMPTY_GOAL_MESSAGE}"
        try:
            from src.agent.manager import manager as agent_manager

            agent_manager.agent_force_push(content=content, type="system_clock")
            print("🔄 [Heartbeat] 心跳到达触发点，已注入 GOAL 内容")
        except Exception as e:
            print(f"❌ [Heartbeat] 心跳注入失败: {e}")

    # ==========================================
    # 历史数据迁移
    # ==========================================
    @staticmethod
    def _migrate_todo_to_goal():
        """旧版 TODO.md 重命名为 GOAL.md（仅当 GOAL.md 不存在时）"""
        todo_path = os.path.join(AGENT_CORE_DIR, "TODO.md")
        try:
            if os.path.exists(todo_path) and not os.path.exists(GOAL_MD_PATH):
                os.replace(todo_path, GOAL_MD_PATH)
                print("[Heartbeat] 已将旧版 TODO.md 迁移为 GOAL.md")
        except OSError as e:
            print(f"[Heartbeat] TODO.md 迁移失败: {e}")


def get_heartbeat_manager() -> HeartbeatManager:
    return HeartbeatManager()

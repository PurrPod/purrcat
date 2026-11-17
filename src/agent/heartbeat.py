"""Agent 心跳：注册到通用定时任务中心（SPEC-034）。

心跳不再自己起线程：把「下一轮什么时候注入 GOAL.md」交给定时服务，
Agent 忙时由 sink 返回 defer 自动顺延。
"""

from __future__ import annotations

import json
import os
import threading
import time

from src.utils._fs import write_json_atomic
from src.utils.config import AGENT_CORE_DIR, GOAL_MD_PATH, HEARTBEAT_FILE

# 最短心跳间隔（秒）
MIN_INTERVAL = 60

# GOAL.md 为空时的兜底注入内容
EMPTY_GOAL_MESSAGE = "当前没有待办事项"

HEARTBEAT_EVENT_ID = "heartbeat"
HEARTBEAT_SOURCE = "heartbeat"


def read_goal() -> str:
    try:
        with open(GOAL_MD_PATH, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        return ""


def heartbeat_content() -> str:
    """到点时实时读取 GOAL.md，拼出注入内容。"""
    goal = read_goal()
    if goal:
        return f"⏰ [Heartbeat] 当前目标 (GOAL.md)：\n{goal}"
    return f"⏰ [Heartbeat] {EMPTY_GOAL_MESSAGE}"


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
        self._cfg_lock = threading.Lock()
        self._cfg = {"interval": 1800, "active": False}
        self._last_mtime = -1.0

    # ==========================================
    # 生命周期
    # ==========================================
    def start(self):
        """幂等：把心跳登记到定时服务（服务未启动时先落盘，启动后生效）。"""
        os.makedirs(AGENT_CORE_DIR, exist_ok=True)
        self._migrate_todo_to_goal()
        self._ensure_config_file()
        self.apply()
        print("🟢 [Heartbeat] 已注册到定时任务中心（GOAL.md 注入驱动）")

    def apply(self):
        """按当前配置增删心跳事件；配置关闭时取消。"""
        cfg = self.get_config()
        from src.timer import get_timer_service

        service = get_timer_service()
        if not cfg["active"]:
            service.cancel(HEARTBEAT_EVENT_ID)
            return
        interval = cfg["interval"]
        service.add_event(
            {
                "id": HEARTBEAT_EVENT_ID,
                "source": HEARTBEAT_SOURCE,
                "target": "main",
                "effect": {"signal": "heartbeat"},
                "at": time.time() + interval,
                "repeat": {"kind": "interval", "seconds": interval},
                "catch_up": "skip",
            }
        )

    # ==========================================
    # 配置读写（单一数据源：heartbeat.json 文件）
    # ==========================================
    def _ensure_config_file(self):
        if not os.path.exists(HEARTBEAT_FILE):
            self._write_config({"interval": 1800, "active": False})

    def _write_config(self, cfg: dict):
        write_json_atomic(HEARTBEAT_FILE, cfg)

    def get_config(self) -> dict:
        """读取心跳配置（mtime 变化时重载，供 API 共用）"""
        with self._cfg_lock:
            try:
                mtime = os.path.getmtime(HEARTBEAT_FILE)
                if mtime != self._last_mtime:
                    with open(HEARTBEAT_FILE, "r", encoding="utf-8") as file:
                        data = json.load(file)
                    self._cfg = {
                        "interval": max(MIN_INTERVAL, int(data.get("interval", 1800))),
                        "active": bool(data.get("active", False)),
                    }
                    self._last_mtime = mtime
            except (FileNotFoundError, json.JSONDecodeError, ValueError):
                self._cfg = {"interval": 1800, "active": False}
                self._last_mtime = -1.0
            return dict(self._cfg)

    read_goal = staticmethod(read_goal)

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
        except OSError as error:
            print(f"[Heartbeat] TODO.md 迁移失败: {error}")


def get_heartbeat_manager() -> HeartbeatManager:
    return HeartbeatManager()

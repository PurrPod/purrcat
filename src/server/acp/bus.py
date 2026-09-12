"""
ACP 事件总线 (server/acp/bus.py)

Agent 主循环（AgentSensorThread，工作线程）里的产出事件 → ACP 网关消费者
（SSE 端点在 asyncio loop / stdio 桥在工作线程）。发布方工作在线程，
订阅方可能持有 asyncio loop：用 call_soon_threadsafe 跨线程投递，
订阅回调异常全部吞掉，绝不让消费者拖崩 Agent 主循环。

事件信封：
    {"type": "agent_message"|"agent_thought"|"tool_call"|"phase"|"turn_end",
     "sessionId": <purrcat session_id>,   # 内部会话，SSE 侧再换算为 ACP sessionId
     "data": {...}, "ts": time.time()}
"""

import threading
import time
import itertools


class AcpEventBus:
    def __init__(self):
        self._lock = threading.RLock()
        self._subs = {}  # sub_id -> {"session": str|None, "callback": fn, "loop": loop|None}
        self._ids = itertools.count(1)

    def subscribe(self, session_id: str | None, callback, loop=None):
        """订阅事件；session_id 为 None 表示订阅全部。返回退订函数。"""
        with self._lock:
            sub_id = next(self._ids)
            self._subs[sub_id] = {
                "session": session_id,
                "callback": callback,
                "loop": loop,
            }

        def _unsubscribe():
            with self._lock:
                self._subs.pop(sub_id, None)

        return _unsubscribe

    def publish(self, session_id: str, event_type: str, data: dict):
        """发布事件（Agent 工作线程调用）。单个消费者异常不影响其它消费者。"""
        envelope = {
            "type": event_type,
            "sessionId": session_id,
            "data": data,
            "ts": time.time(),
        }
        with self._lock:
            subs = list(self._subs.values())
        for sub in subs:
            if sub["session"] is not None and sub["session"] != session_id:
                continue
            self._deliver(sub, envelope)

    @staticmethod
    def _deliver(sub, envelope: dict):
        try:
            loop = sub["loop"]
            cb = sub["callback"]
            if loop is not None:
                # asyncio 消费者：投递到其事件循环；loop 已关闭则静默丢弃
                loop.call_soon_threadsafe(cb, envelope)
            else:
                # 同步消费者（stdio 桥）
                cb(envelope)
        except Exception as e:
            print(f"[ACP Bus] 事件投递失败（已吞）: {e}")


_bus = AcpEventBus()


def get_bus() -> AcpEventBus:
    return _bus

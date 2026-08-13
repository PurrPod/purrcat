import json
import os
import threading
import time

from src.utils.config import LOOP_FILE

LOOP_LOCK = threading.Lock()


class LoopWorker(threading.Thread):
    def __init__(self, loop_id, item):
        super().__init__(daemon=True)
        self.loop_id = loop_id
        self.item = item
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        print(
            f"🟢 [LoopWorker] 循环线程已启动: {self.item.get('title')} (ID: {self.loop_id})"
        )
        while not self._stop_event.is_set():
            interval = int(self.item.get("interval", 1800))
            steps = interval

            while steps > 0 and not self._stop_event.is_set():
                time.sleep(1)
                steps -= 1

            if self._stop_event.is_set():
                break

            task_hook = self.item.get("task_hook", "Agent")
            task_inputs = self.item.get("task_inputs", {})
            title = self.item.get("title", "loop_task")

            print(f"🔄 [LoopManager] 循环任务到达触发点: {title} (Hook: {task_hook})")
            try:
                if task_hook == "Agent":
                    from src.agent.manager import manager as agent_manager

                    agent_manager.agent_force_push(
                        content="⏰ [Heartbeat] Fetch solo todo", type="system_clock"
                    )
                else:
                    import asyncio
                    from src.harness.process import Task

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    task = Task(
                        task_name=title, inputs=task_inputs, graph_name=task_hook
                    )

                    loop.run_until_complete(task.run())
                    loop.close()
                    print(
                        f"✅ [LoopManager] 后台流水线任务执行完毕: {title}，开始重新计算下一次间隔。"
                    )
            except Exception as e:
                print(f"❌ [LoopManager] 循环任务 {title} 运行期间抛出异常: {e}")


class LoopManager:
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
        self.workers = {}
        self._lock = threading.Lock()
        self._running = False

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
        threading.Thread(target=self._watch_loop_json, daemon=True).start()
        print("🟢 [LoopManager] 动态热加载循环任务管理器守护线程已就位")

    def _watch_loop_json(self):
        last_mtime = 0
        os.makedirs(os.path.dirname(LOOP_FILE), exist_ok=True)

        if not os.path.exists(LOOP_FILE):
            default_loops = [
                {
                    "id": "lp_default_heartbeat",
                    "title": "系统心跳",
                    "interval": 1800,
                    "task_hook": "Agent",
                    "task_inputs": {},
                    "active": True,
                }
            ]
            with open(LOOP_FILE, "w", encoding="utf-8") as f:
                json.dump(default_loops, f, indent=2, ensure_ascii=False)

        while self._running:
            try:
                if os.path.exists(LOOP_FILE):
                    mtime = os.path.getmtime(LOOP_FILE)
                    if mtime != last_mtime:
                        time.sleep(0.5)
                        mtime_check = os.path.getmtime(LOOP_FILE)
                        if mtime == mtime_check:
                            last_mtime = mtime
                            self._sync_loops()
            except Exception as e:
                print(f"⚠️ [LoopManager] 监视 loop.json 异常: {e}")
            time.sleep(3)

    def _sync_loops(self):
        try:
            with open(LOOP_FILE, "r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception as e:
            print(f"❌ [LoopManager] 无法解析 loop.json，可能存在语法错误: {e}")
            return

        with self._lock:
            active_ids = set()
            for item in items:
                loop_id = item.get("id")
                if not loop_id:
                    continue

                if item.get("active", False):
                    active_ids.add(loop_id)
                    if loop_id in self.workers:
                        old_worker = self.workers[loop_id]
                        if (
                            old_worker.item.get("interval") != item.get("interval")
                            or old_worker.item.get("task_hook") != item.get("task_hook")
                            or old_worker.item.get("task_inputs")
                            != item.get("task_inputs")
                        ):
                            print(
                                f"🔄 [LoopManager] 检测到 Loop ID: {loop_id} 配置有变，正在热重建..."
                            )
                            old_worker.stop()
                            new_worker = LoopWorker(loop_id, item)
                            self.workers[loop_id] = new_worker
                            new_worker.start()
                    else:
                        print(
                            f"🚀 [LoopManager] 成功捕捉新活跃循环 ID: {loop_id}，拉起独立工作线程..."
                        )
                        worker = LoopWorker(loop_id, item)
                        self.workers[loop_id] = worker
                        worker.start()

            for loop_id in list(self.workers.keys()):
                if loop_id not in active_ids:
                    print(
                        f"🛑 [LoopManager] 循环任务下线或被移除 ID: {loop_id}，优雅终止子线程..."
                    )
                    self.workers[loop_id].stop()
                    del self.workers[loop_id]


def get_loop_manager() -> LoopManager:
    return LoopManager()

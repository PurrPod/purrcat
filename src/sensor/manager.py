import json
import subprocess
import threading
import os
import urllib.request
import urllib.error
import atexit
import sys
from .gateway import get_gateway, RemoteSensorProxy
from src.utils.config import get_sensor_config, SENSOR_EXTENSION_DIR


class SensorManager:
    def __init__(self):
        # 用户扩展传感器目录：~/.purrcat/sensor（内置传感器已移除，仅支持外部扩展）
        self.extension_dir = SENSOR_EXTENSION_DIR
        self.processes = {}
        # 官方传感器仓库 PurrPod/sensors，代码位于 sensors/ 子目录下
        self.github_repo_base = (
            "https://raw.githubusercontent.com/PurrPod/sensors/main/sensors"
        )
        self._watchdog_started = False

        os.makedirs(self.extension_dir, exist_ok=True)

    def _download_and_start_sensor_bg(
        self, sensor_name: str, urls: list, local_path: str, cfg: dict
    ):
        """🌟 后台下载逻辑：依次尝试候选 URL（仓库结构 sensors/<name>/<name>.py 或 sensors/<name>.py）"""
        try:
            last_err = None
            for url in urls:
                try:
                    urllib.request.urlretrieve(url, local_path)
                    print(f"✅ [Manager] {sensor_name} 云端下载完成！")
                    break
                except Exception as e:
                    last_err = e
                    # 清理下载失败的半成品文件，避免被误认为已安装
                    if os.path.exists(local_path):
                        try:
                            os.remove(local_path)
                        except Exception:
                            pass
            else:
                raise last_err or RuntimeError("所有候选 URL 均下载失败")
            # 下载完毕后再启动
            self._start_sensor(sensor_name, local_path, cfg)
        except urllib.error.HTTPError as e:
            print(
                f"❌ [Manager] 下载失败，云端仓库找不到 {sensor_name}.py (HTTP {e.code})"
            )
        except Exception as e:
            print(f"❌ [Manager] 下载 {sensor_name} 失败: {e}")

    def load_and_start_all(self):
        print("🔍 [SensorManager] 正在读取 .purrcat/activate_sensor.json 配置...")

        config = get_sensor_config()

        if not config:
            print("⚠️ [SensorManager] 未检测到有效的 Sensor 配置，已跳过。")
            return

        for name, cfg in config.items():
            is_enabled = cfg.get("enabled", False)

            if not is_enabled:
                print(
                    f"⏸️  [SensorManager] 传感器 '{name}' 已被禁用 (enabled=false)，跳过启动。"
                )
                continue

            local_path = os.path.join(self.extension_dir, f"{name}.py")
            if os.path.exists(local_path):
                self._start_sensor(name, local_path, cfg)
            else:
                # 🌟 重构：开启子线程去下载，绝不阻塞当前循环
                print(f"🔄 [Manager] 本地无 {name}.py，已派发后台下载任务...")
                urls = [
                    f"{self.github_repo_base}/{name}/{name}.py",
                    f"{self.github_repo_base}/{name}.py",
                ]
                threading.Thread(
                    target=self._download_and_start_sensor_bg,
                    args=(name, urls, local_path, cfg),
                    daemon=True,
                ).start()

        if not self._watchdog_started:
            threading.Thread(target=self._watchdog_loop, daemon=True).start()
            self._watchdog_started = True
            print("🛡️ [Manager] 进程守护线程已启动")

    def _start_sensor(self, name: str, script_path: str, cfg: dict):
        env = os.environ.copy()
        env.update(cfg.get("env", {}))
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            command = ["uv", "run", script_path]

            # Windows 下隐藏传感器子进程的终端弹窗（uv/pytest 等都是控制台程序）
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

            process = subprocess.Popen(
                command,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                # 子进程 PYTHONIOENCODING=utf-8，这里必须显式按 UTF-8 解码，
                # 否则 Windows 中文系统默认 GBK 解码，读到多字节 UTF-8 会 UnicodeDecodeError
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
            self.processes[name] = process

            proxy = RemoteSensorProxy(name, cfg.get("capabilities", {}), process.stdin)
            get_gateway().register(proxy)

            threading.Thread(
                target=self._listen_to_stdout, args=(name, process), daemon=True
            ).start()
            threading.Thread(
                target=self._listen_to_stderr, args=(name, process), daemon=True
            ).start()
            print(f"🚀 [Manager] 成功拉起 Sensor 子进程: {name} (PID: {process.pid})")

        except FileNotFoundError:
            print(
                "❌ [Manager] 找不到 'uv' 命令！请先安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
            )
        except Exception as e:
            print(f"❌ [Manager] 启动 {name} 失败: {e}")

    def _listen_to_stdout(self, name: str, process: subprocess.Popen):
        gateway = get_gateway()
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
            try:
                msg = json.loads(line.strip())
                method = msg.get("method")

                if method == "observe":
                    content = msg.get("params", {}).get("content")
                    if content:
                        gateway.push(name, content)
                elif method == "log":
                    print(f"📝 [{name}]: {msg.get('params', {}).get('msg')}")
                elif method == "launch_task":
                    # 解析传来的任务信息
                    params = msg.get("params", {})
                    graph_name = params.get("graph_name")
                    inputs = params.get("inputs", {})
                    title = params.get("title", "cron_task")

                    print(
                        f"🚀 [Manager] 收到时钟触发，准备拉起后台任务图谱: {graph_name}"
                    )

                    # 定义后台执行任务
                    def _run_bg_task():
                        import asyncio
                        from src.harness.process import Task

                        try:
                            # 因为这是在新线程中，需要给它配一个新的独立事件循环
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)

                            # 实例化并运行 Harness 的 Task
                            task = Task(
                                task_name=title, inputs=inputs, graph_name=graph_name
                            )
                            loop.run_until_complete(task.run())
                        except Exception as e:
                            print(f"❌ [Manager] 定时后台任务执行崩溃: {e}")

                    # 通过独立线程启动，防止阻塞 Manager 监听 stdout
                    threading.Thread(target=_run_bg_task, daemon=True).start()
            except json.JSONDecodeError:
                pass

    def _listen_to_stderr(self, name: str, process: subprocess.Popen):
        for line in iter(process.stderr.readline, ""):
            if line:
                print(f"⚠️ [{name} 日志/报错]: {line.strip()}", file=sys.stderr)

    def _watchdog_loop(self):
        import time

        while True:
            time.sleep(10)
            for name, process in list(self.processes.items()):
                if process.poll() is not None:
                    print(
                        f"🚨 [Manager] 检测到 Sensor [{name}] 已退出，清理进程引用并尝试重启..."
                    )

                    del self.processes[name]

                    config = get_sensor_config().get(name, {})
                    local_path = os.path.join(self.extension_dir, f"{name}.py")
                    if os.path.exists(local_path) and config.get("enabled", False):
                        self._start_sensor(name, local_path, config)

    def stop_all(self):
        for name, process in self.processes.items():
            try:
                process.terminate()
            except Exception:
                pass

        self.processes.clear()


_manager = SensorManager()
atexit.register(_manager.stop_all)


def get_manager() -> SensorManager:
    return _manager

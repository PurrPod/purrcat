import json
import subprocess
import threading
import os
import urllib.request
import urllib.error
import atexit
import sys
from .gateway import get_gateway, RemoteSensorProxy
from src.utils.config import get_sensor_config


class SensorManager:
    def __init__(self):
        self.extension_dir = os.path.join(os.path.dirname(__file__), "extension")
        self.processes = {}
        self.github_repo_base = (
            "https://raw.githubusercontent.com/PurrPod/sensor-source/main"
        )

        os.makedirs(self.extension_dir, exist_ok=True)

    def _download_and_start_sensor_bg(self, sensor_name: str, url: str, local_path: str, cfg: dict):
        """🌟 新增：后台下载逻辑"""
        try:
            urllib.request.urlretrieve(url, local_path)
            print(f"✅ [Manager] {sensor_name} 云端下载完成！")
            # 下载完毕后再启动
            self._start_sensor(sensor_name, local_path, cfg)
        except urllib.error.HTTPError as e:
            print(f"❌ [Manager] 下载失败，云端仓库找不到 {sensor_name}.py (HTTP {e.code})")
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
                url = f"{self.github_repo_base}/{name}.py"
                threading.Thread(
                    target=self._download_and_start_sensor_bg,
                    args=(name, url, local_path, cfg),
                    daemon=True,
                ).start()

    def _start_sensor(self, name: str, script_path: str, cfg: dict):
        env = os.environ.copy()
        env.update(cfg.get("env", {}))
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            command = ["uv", "run", script_path]

            process = subprocess.Popen(
                command,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
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
            except json.JSONDecodeError:
                pass

    def _listen_to_stderr(self, name: str, process: subprocess.Popen):
        for line in iter(process.stderr.readline, ""):
            if line:
                print(f"⚠️ [{name} 日志/报错]: {line.strip()}", file=sys.stderr)

    def stop_all(self):
        for name, process in self.processes.items():
            process.terminate()


_manager = SensorManager()
atexit.register(_manager.stop_all)


def get_manager() -> SensorManager:
    return _manager

import json
import subprocess
import threading
import os
import urllib.request
import urllib.error
import atexit
import sys
from .bridge import AcpSensorBridge
from src.utils.config import (
    get_sensor_config,
    get_enriched_env,
    SENSOR_EXTENSION_DIR,
)


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

    def _close_stdin(self, process):
        """显式关闭 stdin 写端：进程死后残留管道若交给 GC，flush 会报 OSError[Errno 22]"""
        try:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
        except Exception:
            pass

    def _kill_process_tree(self, process):
        """整树击杀 sensor 进程。Windows 下 terminate() 只杀 uv 包装进程，
        会留下 sensor python 孤儿——孤儿 bot 会继续重连外部服务（如飞书 WS）
        抢占事件，且其 stdout 已无人监听，事件会被静默吞掉"""
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                process.terminate()
        except Exception:
            pass
        self._close_stdin(process)

    def _start_sensor(self, name: str, script_path: str, cfg: dict):
        # 防御：同名 sensor 已在运行时先整树击杀，避免双实例抢占外部连接
        old = self.processes.get(name)
        if old and old.poll() is None:
            self._kill_process_tree(old)
        # 🌟 合并注册表最新 PATH：用户中途安装 uv 后无需重启程序即可拉起 sensor
        env = get_enriched_env()
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
        bridge: AcpSensorBridge | None = None  # 惰性建桥：首条 JSON-RPC 行到达时
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
            try:
                msg = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            # ACP 方言：JSON-RPC 载荷（有 jsonrpc 键）走 stdio 桥；
            # 其余（旧 observe/express/log 方言已删除）忽略——旧 sensor 请重写
            if "jsonrpc" not in msg:
                print(
                    f"⚠️ [Manager] {name} 输出了非 ACP 方言载荷（已忽略，"
                    "旧协议已移除，请将 sensor 升级为 ACP 方言）: {line.strip()[:120]}"
                )
                continue

            if bridge is None:
                cfg = get_sensor_config().get(name, {})
                bridge = AcpSensorBridge(
                    name,
                    process.stdin,
                    tool_detail=cfg.get("tool_detail", False),
                )
            bridge.handle_line(msg)

        # 进程退出（stdout EOF）：退订桥 + 关 stdin 写端（防 GC flush 报错）
        if bridge is not None:
            bridge.close()
        self._close_stdin(process)

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

                    self._close_stdin(process)
                    del self.processes[name]

                    config = get_sensor_config().get(name, {})
                    local_path = os.path.join(self.extension_dir, f"{name}.py")
                    if os.path.exists(local_path) and config.get("enabled", False):
                        self._start_sensor(name, local_path, config)

    def stop_all(self):
        for name, process in self.processes.items():
            self._kill_process_tree(process)

        self.processes.clear()


_manager = SensorManager()
atexit.register(_manager.stop_all)


def get_manager() -> SensorManager:
    return _manager

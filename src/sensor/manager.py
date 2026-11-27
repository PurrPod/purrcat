import json
import subprocess
import threading
import os
import atexit
import sys
from .bridge import AcpSensorBridge
from .processes import (
    build_sensor_env,
    close_stdin,
    kill_process_tree,
    sensor_command,
)
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
        self._watchdog_started = False

        os.makedirs(self.extension_dir, exist_ok=True)

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
                print(
                    f"❌ [Manager] 本地缺少 {name}.py，Sensor '{name}' 启动失败"
                    f"（不再自动下载，请先安装代码到 {self.extension_dir}）"
                )

        if not self._watchdog_started:
            threading.Thread(target=self._watchdog_loop, daemon=True).start()
            self._watchdog_started = True
            print("🛡️ [Manager] 进程守护线程已启动")

    def _close_stdin(self, process):
        """显式关闭 stdin 写端：进程死后残留管道若交给 GC，flush 会报 OSError[Errno 22]"""
        close_stdin(process)

    def _kill_process_tree(self, process):
        """整树击杀 sensor 进程（Windows 下 terminate 会留下孤儿 python）。"""
        kill_process_tree(process)

    def _start_sensor(self, name: str, script_path: str, cfg: dict):
        # 防御：同名 sensor 已在运行时先整树击杀，避免双实例抢占外部连接
        old = self.processes.get(name)
        if old and old.poll() is None:
            self._kill_process_tree(old)
        # 🌟 合并注册表最新 PATH：用户中途安装 uv 后无需重启程序即可拉起 sensor
        env = build_sensor_env(get_enriched_env(), cfg)

        try:
            command = sensor_command(script_path)

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

    def list_running(self) -> list:
        """列出已登记的 Sensor 进程：[{name, pid, alive}]（alive=false 表示引用尚在但进程已退出）"""
        result = []
        for name, process in self.processes.items():
            result.append(
                {"name": name, "pid": process.pid, "alive": process.poll() is None}
            )
        return sorted(result, key=lambda item: item["name"])

    def stop_sensor(self, name: str) -> bool:
        """停止指定 Sensor：整树击杀并清理引用。

        调用方须同时把配置置为 enabled=false，否则 watchdog 会按配置把它重新拉起。
        返回是否命中一个已登记的进程。
        """
        process = self.processes.pop(name, None)
        if process is None:
            return False
        self._kill_process_tree(process)
        self._close_stdin(process)
        print(f"🛑 [Manager] 已停止 Sensor 子进程: {name} (PID: {process.pid})")
        return True

    def restart_sensor(self, name: str) -> bool:
        """重启单个 Sensor：整树击杀同名旧进程，再按当前配置重新拉起。

        返回是否成功把新进程登记进线程池（本地缺 <name>.py、或 uv 拉起失败时为 False）。
        """
        config = get_sensor_config().get(name, {})
        script_path = os.path.join(self.extension_dir, f"{name}.py")
        old = self.processes.pop(name, None)
        if old is not None:
            self._kill_process_tree(old)
        if not os.path.exists(script_path):
            print(f"❌ [Manager] 重启 {name} 失败：本地未找到 {script_path}")
            return False
        self._start_sensor(name, script_path, config)
        return name in self.processes


_manager = SensorManager()
atexit.register(_manager.stop_all)


def get_manager() -> SensorManager:
    return _manager

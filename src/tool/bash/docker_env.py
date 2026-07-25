import atexit
import os
import re
import sys
import threading
import uuid
from typing import Optional

import docker
import pexpect
from docker.errors import DockerException, ImageNotFound, NotFound

from src.utils.config import get_engine_preference

from .exceptions import (
    BashTimeoutError,
    DockerImageNotFoundError,
    DockerNotRunningError,
)

if sys.platform == "win32":
    from pexpect.popen_spawn import PopenSpawn

    SpawnClass = PopenSpawn

    def check_alive(p):
        if p is None:
            return False
        return p.proc.poll() is None

    def force_close(p):
        if p is None:
            return
        try:
            import signal

            p.kill(signal.SIGTERM)
        except Exception:
            pass


else:
    SpawnClass = pexpect.spawn

    def check_alive(p):
        if p is None:
            return False
        return p.isalive()

    def force_close(p):
        if p is None:
            return
        p.close(force=True)


def _get_container_exec_cmd(container_name: str) -> str:
    engine = get_engine_preference()
    if sys.platform == "win32":
        return f"{engine} exec -i {container_name} /bin/bash"
    else:
        return f"{engine} exec -it {container_name} /bin/bash"


_docker_manager_instance: Optional["DockerManager"] = None


def _get_container_env() -> dict:
    # 既然主机开了 TUN 模式，容器不需要任何代理环境变量，直接跟主机共享网络上下文
    return {}


class DockerManager:
    def __init__(
        self,
        image: str,
        container_name: str = "agent_computer",
        workspace_dir: str | None = None,
    ):
        if not image:
            raise ValueError("A Docker image must be provided.")

        engine_preference = get_engine_preference()

        if engine_preference in ["docker", "podman"]:
            import shutil

            if shutil.which(engine_preference):
                self.engine = engine_preference
            else:
                raise DockerNotRunningError(
                    f"全局配置中指定了 {engine_preference}，但系统未检测到该命令，请重新执行 purrcat setup"
                )
        else:
            import shutil

            self.engine = shutil.which("podman") or shutil.which("docker")
            if not self.engine:
                raise DockerNotRunningError(
                    "未检测到任何容器环境，请先执行 purrcat setup"
                )

        print(f"🔧 使用容器引擎: {self.engine}")

        try:
            self.client = docker.from_env()
        except Exception as e:
            raise DockerNotRunningError(
                f"{self.engine.capitalize()} 客户端初始化失败: {e}"
            )

        self.image = image
        self.container_name = container_name
        self.workspace_dir = workspace_dir
        self.container_workspace = "/agent_vm"
        self.container = None
        self.shell_pool = {}
        self.pool_lock = threading.Lock()
        self._started = False

    def start(self):
        if self._started and self.container is not None:
            try:
                self.container.reload()
                if self.container.status == "running":
                    print(f"[*] 复用已有沙盒 ({self.container_name})，状态: running")
                    return
            except Exception:
                pass

        if self._started:
            print(f"[-] 沙盒 ({self.container_name}) 状态异常，尝试重启...")

        # ---------- 替换旧容器清理逻辑：唤醒休眠容器 ----------
        try:
            existing_container = self.client.containers.get(self.container_name)
            if existing_container.status != "running":
                print(f"[-] 发现休眠沙盒 ({self.container_name})，正在唤醒...")
                existing_container.start()
            else:
                print(f"[*] 专属沙盒 ({self.container_name}) 已在运行。")

            self.container = existing_container
            self._started = True
            return  # 成功复用已有容器，直接返回，不再执行后面的 run 创建逻辑

        except NotFound:
            print(
                f"🚀 未找到沙盒 ({self.container_name})，将基于镜像 {self.image} 创建全新虚拟机..."
            )
            pass  # 继续往下走原来的创建代码
        except DockerException as e:
            raise DockerNotRunningError(f"{self.engine.capitalize()} API 连接失败: {e}")

        env_vars = _get_container_env()

        run_kwargs = {
            "name": self.container_name,
            "command": "sleep infinity",
            "detach": True,
            "working_dir": self.container_workspace,
            "environment": env_vars,
            "extra_hosts": {"host.docker.internal": "host-gateway"},
            "shm_size": "2gb",
            "cap_add": ["SYS_ADMIN"],
            "security_opt": ["seccomp=unconfined"],
        }

        volumes = {}
        if self.workspace_dir is not None:
            os.makedirs(self.workspace_dir, exist_ok=True)
            volumes[os.path.abspath(self.workspace_dir)] = {
                "bind": self.container_workspace,
                "mode": "rw",
            }

        run_kwargs["volumes"] = volumes

        try:
            print(f"🚀 正在基于镜像 {self.image} 创建全新沙盒...")
            self.container = self.client.containers.run(self.image, **run_kwargs)

            if env_vars.get("HTTP_PROXY"):
                proxy_url = env_vars["HTTP_PROXY"]
                print(
                    f"🌐 检测到代理环境，正在为容器内部 apt 注入代理配置: {proxy_url}"
                )
                apt_cmd = f'sh -c \'echo "Acquire::http::Proxy \\"{proxy_url}\\";\\nAcquire::https::Proxy \\"{proxy_url}\\";" > /etc/apt/apt.conf.d/99proxy\''
                self.container.exec_run(apt_cmd, user="root")

            self._started = True
            print("✅ 全新沙盒环境启动就绪！")
        except ImageNotFound:
            raise DockerImageNotFoundError(f"找不到镜像: {self.image}")
        except DockerException as e:
            raise DockerImageNotFoundError(f"容器启动异常: {e}")

    def stop(self):
        with self.pool_lock:
            active_session_ids = list(self.shell_pool.keys())
        for sid in active_session_ids:
            self.close_shell(sid)

        if self.container:
            try:
                print(f"[-] 正在让沙盒 ({self.container_name}) 休眠...")
                self.container.stop(timeout=2)
                print("[*] 沙盒已休眠，所有的依赖安装和系统变更已被保留")
            except Exception as e:
                print(f"[*] 休眠沙盒失败: {e}")

        self.container = None

    def _ensure_shell(self, session_id: str):
        if not self.container:
            raise RuntimeError("Container not running.")

        if session_id in self.shell_pool:
            return

        print(f"[+] Auto-creating new shell session: '{session_id}'")
        command = _get_container_exec_cmd(self.container.name)
        try:
            shell_process = SpawnClass(command, encoding="utf-8", timeout=120)
            shell_process.send(
                "stty -echo\nexport PS1=''\nexport TERM=dumb\necho '__SHELL_READY__'\n"
            )
            shell_process.expect("__SHELL_READY__", timeout=10)

            with self.pool_lock:
                if session_id in self.shell_pool:
                    force_close(shell_process)
                    return
                self.shell_pool[session_id] = {
                    "process": shell_process,
                    "lock": threading.Lock(),
                }
        except pexpect.exceptions.TIMEOUT:
            raise RuntimeError("Timeout initializing shell environment.")

    def close_shell(self, session_id: str):
        with self.pool_lock:
            session = self.shell_pool.pop(session_id, None)
        if session:
            with session["lock"]:
                process = session["process"]
                if check_alive(process):
                    force_close(process)
            print(f"[-] Shell session closed: {session_id}")

    def _restart_shell(self, session_id: str):
        session = self.shell_pool.get(session_id)
        if not session:
            return
        if check_alive(session["process"]):
            force_close(session["process"])
        command = _get_container_exec_cmd(self.container.name)
        new_process = SpawnClass(command, encoding="utf-8", timeout=120)
        new_process.send(
            "stty -echo\nexport PS1=''\nexport TERM=dumb\necho '__SHELL_READY__'\n"
        )
        new_process.expect("__SHELL_READY__", timeout=10)
        session["process"] = new_process

    def execute(
        self, session_id: str, command: str, timeout: int = 300
    ) -> tuple[int, str, str]:
        self._ensure_shell(session_id)
        with self.pool_lock:
            session = self.shell_pool[session_id]

        with session["lock"]:
            process = session["process"]
            if not check_alive(process):
                print(f"[yellow]Shell '{session_id}' died. Restarting...[/yellow]")
                self._restart_shell(session_id)
                process = session["process"]

            marker_id = uuid.uuid4().hex
            marker_str = f"__CMD_DONE_{marker_id}__"
            # 新代码：将大模型的命令包在一个代码块中，并强制将其输入重定向到 /dev/null
            # 这样无论里面跑什么命令，都无法窃取终端后续的输入字符
            safe_command = command.strip()
            full_payload = f'{{ {safe_command} ; }} < /dev/null\necho -e "\\n{marker_str}$?|$(pwd)"'

            process.send(full_payload.replace("\r", "") + "\n")
            try:
                process.expect(f"{marker_str}(\\d+)\\|(.*)", timeout=timeout)
            except pexpect.exceptions.TIMEOUT:
                partial_output = self._clean_ansi(process.before or "")
                print(f"[red]⚠️ Shell '{session_id}' timed out. Resetting...[/red]")
                self._restart_shell(session_id)
                raise BashTimeoutError(f"部分输出:\n{partial_output.strip()}")

            exit_code = int(process.match.group(1))
            cwd = process.match.group(2).strip()
            cleaned_output = self._clean_ansi(process.before).strip()
            lines = [
                line
                for line in cleaned_output.splitlines()
                if line.strip() != command.strip()
            ]
            final_output = "\n".join(lines).strip()
            return exit_code, final_output, cwd

    def _clean_ansi(self, text: str) -> str:
        text = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])").sub("", text)
        return text.replace("\r", "")


def get_docker_manager() -> "DockerManager":
    global _docker_manager_instance
    if _docker_manager_instance is None:
        _docker_manager_instance = DockerManager(
            image="my_agent_env:latest", workspace_dir="./agent_vm"
        )
        atexit.register(_docker_manager_instance.stop)

    _docker_manager_instance.start()
    return _docker_manager_instance

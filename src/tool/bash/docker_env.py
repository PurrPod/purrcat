import atexit
import os
import re
import sys
import threading
import urllib.parse
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
    try:
        from src.utils.config import get_file_config

        cfg = get_file_config().get("docker", {})
        raw_proxy = (
            cfg.get("http_proxy")
            or cfg.get("all_proxy")
            or os.getenv("http_proxy")
            or os.getenv("all_proxy")
            or os.getenv("HTTP_PROXY")
            or os.getenv("ALL_PROXY")
        )

        if not raw_proxy:
            return {}

        parsed = urllib.parse.urlparse(raw_proxy)
        if parsed.hostname in ["127.0.0.1", "localhost"]:
            new_netloc = f"host.docker.internal:{parsed.port}"
            parsed = parsed._replace(netloc=new_netloc)
            proxy_url = urllib.parse.urlunparse(parsed)
        else:
            proxy_url = raw_proxy

        return {
            "HTTP_PROXY": proxy_url,
            "HTTPS_PROXY": proxy_url,
            "ALL_PROXY": proxy_url,
            "http_proxy": proxy_url,
            "https_proxy": proxy_url,
            "all_proxy": proxy_url,
            "NO_PROXY": "localhost,127.0.0.1,::1",
        }
    except Exception as e:
        print(f"⚠️ 代理配置解析失败，退回直连模式: {e}")
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
                    print(f"✅ 复用已有沙盒 ({self.container_name})，状态: running")
                    return
            except Exception:
                pass

        if self._started:
            print(f"⚠️ 沙盒 ({self.container_name}) 状态异常，尝试重启...")

        try:
            old_container = self.client.containers.get(self.container_name)
            print(f"🧹 发现残留的旧沙盒 ({self.container_name})，正在强制清理...")
            old_container.remove(force=True, v=True)
            print("✨ 残留沙盒清理完毕。")
        except NotFound:
            pass
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

        from src.utils.config import SKILL_DIR

        skill_host_dir = SKILL_DIR
        os.makedirs(skill_host_dir, exist_ok=True)
        volumes[skill_host_dir] = {
            "bind": f"{self.container_workspace}/skills",
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
                repo_name = self.image.split(":")[0]
                print(
                    f"🫡 检测到系统退出/异常，正在自动固化环境到 {repo_name}:latest ..."
                )
                self.container.commit(repository=repo_name, tag="latest")
                print("✅ 环境自动保存成功！")
            except Exception as e:
                print(f"⚠️ 自动保存环境失败: {e}")

            try:
                print(f"🛑 正在关闭并清理 Docker 沙盒 ({self.container_name})...")
                self.container.stop(timeout=2)
                self.container.remove(v=True, force=True)
                print("✅ 沙盒已成功关闭并清理。")
            except Exception as e:
                print(f"⚠️ 关闭/清理沙盒容器失败: {e}")

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
            full_payload = f'{command.strip()}\necho -e "\\n{marker_str}$?|$(pwd)"'

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

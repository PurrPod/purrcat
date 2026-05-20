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

from src.utils.config import get_file_config

# 引入自定义异常
from .exceptions import (
    BashTimeoutError,
    DockerImageNotFoundError,
    DockerNotRunningError,
)

# 平台适配逻辑 - 与原代码完全一致
if sys.platform == "win32":
    from pexpect.popen_spawn import PopenSpawn

    SpawnClass = PopenSpawn
    DOCKER_EXEC_CMD = "docker exec -i {container_name} /bin/bash"

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
    DOCKER_EXEC_CMD = "docker exec -it {container_name} /bin/bash"

    def check_alive(p):
        if p is None:
            return False
        return p.isalive()

    def force_close(p):
        if p is None:
            return
        p.close(force=True)


_docker_manager_instance: Optional["DockerManager"] = None


def _get_docker_env() -> dict:
    """自动获取宿主机代理，并转换为跨平台 Docker 可用的格式"""
    try:
        # 1. 尝试从配置文件读取，如果没有，再尝试从宿主机环境变量读取
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
            return {}  # 宿主机没开梯子，直接返回空，容器自然就是直连

        # 2. 解析 URL，如果是 127.0.0.1 或 localhost，则替换为 host.docker.internal
        parsed = urllib.parse.urlparse(raw_proxy)
        if parsed.hostname in ["127.0.0.1", "localhost"]:
            # 保留原有的端口和协议，只替换 host
            new_netloc = f"host.docker.internal:{parsed.port}"
            parsed = parsed._replace(netloc=new_netloc)
            proxy_url = urllib.parse.urlunparse(parsed)
        else:
            # 如果配置的是局域网真实 IP (如 192.168.1.5)，则直接使用
            proxy_url = raw_proxy

        # 3. 返回全套环境变量（大小写全给，兼容不同软件的脾气）
        return {
            "HTTP_PROXY": proxy_url,
            "HTTPS_PROXY": proxy_url,
            "ALL_PROXY": proxy_url,
            "http_proxy": proxy_url,
            "https_proxy": proxy_url,
            "all_proxy": proxy_url,
            "NO_PROXY": "localhost,127.0.0.1,::1",  # 防止容器内部服务互相调用时走代理
        }
    except Exception as e:
        print(f"⚠️ 代理配置解析失败，退回直连模式: {e}")
        return {}


class DockerManager:
    """Docker 沙盒管理器"""

    def __init__(
        self,
        image: str,
        container_name: str = "agent_computer",
        workspace_dir: str | None = None,
    ):
        if not image:
            raise ValueError("A Docker image must be provided.")
        try:
            self.client = docker.from_env()
        except Exception as e:
            raise DockerNotRunningError(f"Docker 客户端初始化失败: {e}")

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
            raise DockerNotRunningError(f"Docker API 连接失败: {e}")

        env_vars = _get_docker_env()

        run_kwargs = {
            "name": self.container_name,
            "command": "sleep infinity",
            "detach": True,
            "working_dir": self.container_workspace,
            "environment": env_vars,
            # === 兼容三大系统与复杂环境的核心魔法 ===
            # 魔法 1：让 Linux 原生 Docker 强制支持 host.docker.internal！Win/Mac 会自动兼容。
            "extra_hosts": {"host.docker.internal": "host-gateway"},
            # 魔法 2：给足共享内存，防止 Chrome/Electron 崩溃
            "shm_size": "2gb",
            # 魔法 3：解除系统调用限制，供复杂沙箱软件使用
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

        from src.utils.config import get_file_config

        docker_mount = get_file_config().get("docker_mount", [])
        for dirpath in docker_mount:
            new_host_dir = os.path.abspath(dirpath)
            os.makedirs(new_host_dir, exist_ok=True)
            target_name = os.path.basename(os.path.normpath(dirpath))
            container_bind_path = f"{self.container_workspace}/{target_name}"
            volumes[new_host_dir] = {"bind": container_bind_path, "mode": "rw"}

        run_kwargs["volumes"] = volumes

        try:
            print(f"🚀 正在基于镜像 {self.image} 创建全新沙盒...")
            self.container = self.client.containers.run(self.image, **run_kwargs)

            # === 新增：为 apt-get 动态注入代理配置 ===
            if env_vars.get("HTTP_PROXY"):
                proxy_url = env_vars["HTTP_PROXY"]
                print(
                    f"🌐 检测到代理环境，正在为容器内部 apt 注入代理配置: {proxy_url}"
                )
                # 写入 apt 代理配置，解决 apt 忽略环境变量的顽疾
                apt_cmd = f'sh -c \'echo "Acquire::http::Proxy \\"{proxy_url}\\";\\nAcquire::https::Proxy \\"{proxy_url}\\";" > /etc/apt/apt.conf.d/99proxy\''
                self.container.exec_run(apt_cmd, user="root")
            # ======================================

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
            # === 新增：退出/异常前自动 Commit 逻辑 ===
            try:
                # 自动提取镜像名，默认打上 latest 标签覆盖
                repo_name = self.image.split(":")[0]
                print(
                    f"� 检测到系统退出/异常，正在自动固化环境到 {repo_name}:latest ..."
                )
                self.container.commit(repository=repo_name, tag="latest")
                print("✅ 环境自动保存成功！")
            except Exception as e:
                print(f"⚠️ 自动保存环境失败: {e}")
            # ==========================================

            try:
                print(f"�� 正在关闭并清理 Docker 沙盒 ({self.container_name})...")
                self.container.stop(timeout=2)
                # 推荐加上 remove() 彻底清理旧容器，保证下次启动时一定是基于最新镜像的干净状态
                self.container.remove(v=True, force=True)
                print("✅ 沙盒已成功关闭并清理。")
            except Exception as e:
                print(f"⚠️ 关闭/清理沙盒容器失败: {e}")

        self.container = None

    def _ensure_shell(self, session_id: str):
        if not self.container:
            raise RuntimeError("Container not running.")
        
        # 第一层检查（无锁，快速返回）
        if session_id in self.shell_pool:
            return
        
        print(f"[+] Auto-creating new shell session: '{session_id}'")
        command = DOCKER_EXEC_CMD.format(container_name=self.container.name)
        try:
            # 【修复】将耗时的进程启动移出锁外部，只在最后更新字典时加锁
            shell_process = SpawnClass(command, encoding="utf-8", timeout=120)
            shell_process.send(
                "stty -echo\nexport PS1=''\nexport TERM=dumb\necho '__SHELL_READY__'\n"
            )
            shell_process.expect("__SHELL_READY__", timeout=10)
            
            with self.pool_lock:
                # 第二层检查（防止并发创建了多个同名 session）
                if session_id in self.shell_pool:
                    force_close(shell_process)  # 销毁多余的
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
        command = DOCKER_EXEC_CMD.format(container_name=self.container.name)
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
                # 发生超时时不再返回 -1，而是直接抛出特定的超时异常
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

    # 移除宽泛的 try-except 拦截，让明确的异常穿透到 bash.py
    _docker_manager_instance.start()
    return _docker_manager_instance

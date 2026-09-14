import atexit
import multiprocessing
import os
import re
import shutil
import sys
import threading
import uuid
from typing import Optional

import docker
import pexpect
from docker.errors import DockerException, ImageNotFound, NotFound

from src.utils.config import AGENT_VM_DIR
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


_DOCKER_CMD = None


def _resolve_docker_cmd() -> str:
    """返回 docker 可执行文件的绝对路径（仅解析一次），找不到抛出异常"""
    global _DOCKER_CMD
    if _DOCKER_CMD is None:
        path = shutil.which("docker")
        if not path:
            raise RuntimeError(
                "未检测到 docker 命令，请先安装 Docker Desktop。\n"
                "安装指引: https://docs.docker.com/get-docker/"
            )
        _DOCKER_CMD = path
    return _DOCKER_CMD


def _get_container_exec_cmd(container_name: str) -> str:
    docker = _resolve_docker_cmd()
    if sys.platform == "win32":
        return f"{docker} exec -i {container_name} /bin/bash"
    else:
        return f"{docker} exec -it {container_name} /bin/bash"


_docker_manager_instance: Optional["DockerManager"] = None

# 共享专属沙盒的容器名（start/stop 逻辑都以它为准）
SANDBOX_CONTAINER_NAME = "agent_computer"


def _stop_sandbox_on_exit():
    """主进程退出时把沙盒容器休眠（保留容器内的系统变更，进程不残留运行）。

    只能由真正的宿主（MainProcess）注册：bash 工具在子进程隔离下每次调用都会
    新建进程，若让子进程 atexit 去 stop 容器，会在其它并发会话的命令执行到一半时
    切断其 docker exec 连接，造成随机的 End Of File (EOF) 报错。
    """
    try:
        client = docker.from_env(timeout=5)
        container = client.containers.get(SANDBOX_CONTAINER_NAME)
        if container.status == "running":
            container.stop(timeout=2)
            print(f"[*] 宿主退出：沙盒 ({SANDBOX_CONTAINER_NAME}) 已休眠")
    except Exception as e:
        print(f"[*] 宿主退出时休眠沙盒失败(忽略): {e}")


if multiprocessing.current_process().name == "MainProcess":
    # 只有主进程注册退出清理；spawn 出来的 bash 子进程不应休眠共享容器
    atexit.register(_stop_sandbox_on_exit)


def _get_container_env() -> dict:
    # 既然主机开了 TUN 模式，容器不需要任何代理环境变量，直接跟主机共享网络上下文
    return {}


class DockerManager:
    def __init__(
        self,
        image: str,
        container_name: str = SANDBOX_CONTAINER_NAME,
        workspace_dir: str | None = None,
    ):
        if not image:
            raise ValueError("A Docker image must be provided.")

        self.engine = _resolve_docker_cmd()
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

    def _get_container_mount_source(self, container) -> str | None:
        """读取容器 /agent_vm 挂载的宿主机源路径（读不到返回 None）"""
        try:
            mounts = container.attrs.get("Mounts") or []
            for m in mounts:
                if m.get("Destination") == self.container_workspace:
                    return m.get("Source")
        except Exception:
            pass
        return None

    @staticmethod
    def _norm_mount_path(p: str) -> str:
        r"""挂载路径归一化：D:/x、d:/x、/d/x 统一成 d 盘反斜杠形式（大小写不敏感）"""
        p = str(p).replace("/", os.sep)
        # Docker Desktop 偶尔记录成 /d/x 形式（盘符风格），转成 d:\x
        if len(p) >= 3 and p[0] == os.sep and p[1].isalpha() and p[2] == os.sep:
            p = p[1] + ":" + p[2:]
        return os.path.normpath(p).lower()

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

            # 🌟 挂载校验：数据根目录变更后（换盘），旧容器的 /agent_vm
            # 还挂着旧路径，复用会造成"沙盒写了、宿主看不到"的读写错位，
            # 必须销毁重建（容器内系统变更随销毁丢失，属预期）
            if self.workspace_dir is not None:
                existing_container.reload()
                mount_src = self._get_container_mount_source(existing_container)
                want_src = os.path.abspath(self.workspace_dir)
                if mount_src is not None and self._norm_mount_path(
                    mount_src
                ) != self._norm_mount_path(want_src):
                    print(
                        f"⚠️ 沙盒 ({self.container_name}) 挂载错位: 容器挂 {mount_src}，"
                        f"当前数据根要求 {want_src}，销毁重建..."
                    )
                    if existing_container.status == "running":
                        existing_container.stop(timeout=2)
                    existing_container.remove(force=True)
                    raise NotFound("mount mismatch, force recreate")

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
            # 暴露常见前端开发服务器端口到宿主机高位端口，避免与宿主机本地服务冲突
            # 容器端口 -> 宿主机端口（监听 0.0.0.0）
            "ports": {
                "3000/tcp": ("0.0.0.0", 13000),  # Next.js / React 默认端口
                "5173/tcp": ("0.0.0.0", 15173),  # Vite 默认端口
                "8080/tcp": ("0.0.0.0", 18080),  # Vue CLI / Webpack 默认端口
            },
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

    def _spawn_shell_process(self):
        """创建一条新的 docker exec bash 会话，并完成就绪握手。"""
        command = _get_container_exec_cmd(self.container.name)
        shell_process = None
        try:
            shell_process = SpawnClass(command, encoding="utf-8", timeout=120)
            shell_process.send(
                "stty -echo\nexport PS1=''\nexport TERM=dumb\necho '__SHELL_READY__'\n"
            )
            shell_process.expect("__SHELL_READY__", timeout=10)
            return shell_process
        except (pexpect.exceptions.TIMEOUT, pexpect.exceptions.EOF) as e:
            if shell_process is not None:
                try:
                    force_close(shell_process)
                except Exception:
                    pass
            raise RuntimeError(f"沙盒 shell 会话创建失败(容器可能未就绪): {e}") from e

    def _ensure_shell(self, session_id: str):
        if not self.container:
            raise RuntimeError("Container not running.")

        if session_id in self.shell_pool:
            return

        print(f"[+] Auto-creating new shell session: '{session_id}'")
        shell_process = self._spawn_shell_process()
        with self.pool_lock:
            if session_id in self.shell_pool:
                force_close(shell_process)
                return
            self.shell_pool[session_id] = {
                "process": shell_process,
                "lock": threading.Lock(),
            }

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
        session["process"] = self._spawn_shell_process()

    def execute(
        self, session_id: str, command: str, timeout: int = 30
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

            # 通过换行分隔，避免 `{ ` 和 ` ; } < /dev/null` 污染命令末尾的 Heredoc 终结符
            safe_command = command.strip()
            eof_retried = False
            while True:
                marker_id = uuid.uuid4().hex
                marker_str = f"__CMD_DONE_{marker_id}__"
                # 将大模型的命令包在一个代码块中，并强制将其输入重定向到 /dev/null
                # 这样无论里面跑什么命令，都无法窃取终端后续的输入字符
                full_payload = (
                    f"{{\n{safe_command}\n}} < /dev/null\n"
                    f'echo -e "\\n{marker_str}$?|$(pwd)"'
                )

                process.send(full_payload.replace("\r", "") + "\n")
                try:
                    process.expect(f"{marker_str}(\\d+)\\|(.*)", timeout=timeout)
                    break
                except pexpect.exceptions.TIMEOUT:
                    partial_output = self._clean_ansi(process.before or "")
                    print(f"[red]⚠️ Shell '{session_id}' timed out. Resetting...[/red]")
                    self._restart_shell(session_id)
                    process = session["process"]
                    raise BashTimeoutError(f"部分输出:\n{partial_output.strip()}")
                except pexpect.exceptions.EOF as e:
                    # docker exec 会话被意外切断（如容器被并发 stop / Docker 引擎抖动）：
                    # 重启会话后重试一次，避免把偶发掉线直接暴露给上层
                    partial_output = self._clean_ansi(process.before or "")
                    if eof_retried:
                        raise RuntimeError(
                            "沙盒 shell 会话意外断开(EOF)，重启重试后仍失败。\n"
                            f"断开前部分输出:\n{partial_output.strip()}"
                        ) from e
                    eof_retried = True
                    print(
                        f"[yellow]⚠️ Shell '{session_id}' 会话断开(EOF)，"
                        "正在重启会话并重试命令...[/yellow]"
                    )
                    self._restart_shell(session_id)
                    process = session["process"]

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
            image="my_agent_env:latest", workspace_dir=AGENT_VM_DIR
        )
        # 注意：不再在此处注册 atexit 休眠容器。bash 工具在子进程隔离下每次
        # 调用都会新建进程，若每个子进程退出时都 stop 共享容器，会切断其它并发
        # 会话正在执行的 docker exec 连接 → 随机 End Of File (EOF)。
        # 容器休眠统一由模块顶部 MainProcess 的退出钩子负责。

    _docker_manager_instance.start()
    return _docker_manager_instance

import os
import sys
import json
import uuid
import re
import threading
from typing import Optional, Any

import docker
import pexpect
from docker.errors import DockerException, NotFound

# ==========================================
# 0. 跨平台兼容层 (Windows / Linux / Mac)
# ==========================================

if sys.platform == 'win32':
    from pexpect.popen_spawn import PopenSpawn
    SpawnClass = PopenSpawn
    DOCKER_EXEC_CMD = "docker exec -i {container_name} /bin/bash"

    def check_alive(p):
        """Windows: 通过底层的 subprocess.Popen 检查进程状态"""
        if p is None: return False
        return p.proc.poll() is None

    def force_close(p):
        """Windows: 使用 kill 终止进程"""
        if p is None: return
        try:
            import signal
            p.kill(signal.SIGTERM)
        except Exception:
            pass
else:
    SpawnClass = pexpect.spawn
    DOCKER_EXEC_CMD = "docker exec -it {container_name} /bin/bash"

    def check_alive(p):
        """Linux/Mac: 直接使用原生的 isalive"""
        if p is None: return False
        return p.isalive()

    def force_close(p):
        """Linux/Mac: 强制关闭"""
        if p is None: return
        p.close(force=True)

# ==========================================
# 1. 统一的响应格式和懒加载管理
# ==========================================

_docker_manager_instance: Optional['DockerManager'] = None


def _format_response(msg_type: str, content: Any) -> str:
    """与其他插件一致的返回格式"""
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def _get_manager() -> 'DockerManager':
    """
    懒加载并包含重试机制：
    每次调用插件接口时，都会经过此处。它会保证 manager 存在，且尝试 start。
    如果容器关闭了，start() 会静默拉起，从而实现“先自己试试，不直接报错”的容错。
    """
    global _docker_manager_instance
    if _docker_manager_instance is None:
        # 注意：这里的镜像和工作区可根据你的实际情况改成从配置文件读取
        _docker_manager_instance = DockerManager(
            image="my_agent_env:latest",
            container_name="agent_computer",
            workspace_dir=os.path.abspath("./my_project")
        )

    # 每次获取实例都检测并确保容器处于 running 状态
    try:
        _docker_manager_instance.start()
    except Exception as e:
        raise RuntimeError(f"Docker 容器唤醒失败: {str(e)}")

    return _docker_manager_instance


# ==========================================
# 2. 提供给大模型 / Agent 的对外接口
# ==========================================

def execute_command(command: str, session_id: str = "default", timeout: int = 300) -> str:
    """
    提供给大模型：在指定的 Shell 会话中执行命令。
    如果不指定 session_id，则默认使用 'default'。如果该会话不存在，会自动创建。
    """
    try:
        manager = _get_manager()
        exit_code, output, cwd = manager.execute(session_id, command, timeout)

        result = {
            "session_id": session_id,
            "exit_code": exit_code,
            "output": output,
            "cwd": cwd
        }

        # 使用 warning 提示大模型命令可能出错（但仍返回具体报错供它自我修正）
        if exit_code != 0:
            return _format_response("warning", result)

        return _format_response("text", result)
    except Exception as e:
        return _format_response("error", f"Command execution failed: {str(e)}")


def close_shell(session_id: str = "default") -> str:
    """提供给大模型：关闭并释放指定的 Shell 会话"""
    try:
        manager = _get_manager()
        manager.close_shell(session_id)
        return _format_response("text", f"Shell session '{session_id}' successfully closed.")
    except Exception as e:
        return _format_response("error", f"Failed to close shell: {str(e)}")


# ==========================================
# 3. 核心管理器实现 (包含持久化容器与自动会话逻辑)
# ==========================================

class DockerManager:
    def __init__(
            self,
            image: str,
            container_name: str = "agent_computer",
            workspace_dir: str | None = None,
    ):
        if not image:
            raise ValueError("A Docker image must be provided.")
        self.client = docker.from_env()
        self.image = image
        self.container_name = container_name
        self.workspace_dir = workspace_dir
        self.container_workspace = "/workspace"
        self.container = None

        self.shell_pool = {}  # 格式: { session_id: {"process": SpawnClass, "lock": threading.Lock()} }
        self.pool_lock = threading.Lock()  # 用于保护 shell_pool 字典本身的增删

    def start(self):
        """
        初始化与重试检测逻辑：
        判断容器 agent_computer 是否存在、是否运行。缺什么补什么。
        """
        try:
            self.container = self.client.containers.get(self.container_name)
            if self.container.status != "running":
                self.container.start()
        except NotFound:
            run_kwargs = {
                "name": self.container_name,
                "command": "sleep infinity",
                "detach": True,
                "working_dir": self.container_workspace,
            }
            if self.workspace_dir is not None:
                os.makedirs(self.workspace_dir, exist_ok=True)
                run_kwargs["volumes"] = {
                    os.path.abspath(self.workspace_dir): {
                        "bind": self.container_workspace,
                        "mode": "rw"
                    },
                }
            self.container = self.client.containers.run(self.image, **run_kwargs)
        except DockerException as e:
            raise RuntimeError(f"Docker API error: {e}")

    def stop(self):
        """关闭后端时的清理钩子：仅关闭会话，不销毁容器，保证后台持久化"""
        with self.pool_lock:
            active_session_ids = list(self.shell_pool.keys())
        for sid in active_session_ids:
            self.close_shell(sid)
        self.container = None

    def _ensure_shell(self, session_id: str):
        """内部方法：确保指定的 session_id 存在，不存在则自动创建"""
        if not self.container:
            raise RuntimeError("Container not running.")

        with self.pool_lock:
            if session_id in self.shell_pool:
                return  # 已经存在，直接返回

            print(f"[+] Auto-creating new shell session: '{session_id}'")
            command = DOCKER_EXEC_CMD.format(container_name=self.container.name)
            try:
                shell_process = SpawnClass(command, encoding="utf-8", timeout=120)
                init_cmds = (
                    "stty -echo\n"
                    "export PS1=''\n"
                    "export TERM=dumb\n"
                    "echo '__SHELL_READY__'\n"
                )
                shell_process.sendline(init_cmds)
                shell_process.expect("__SHELL_READY__", timeout=10)

                self.shell_pool[session_id] = {
                    "process": shell_process,
                    "lock": threading.Lock()
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
        new_process.sendline("stty -echo\nexport PS1=''\nexport TERM=dumb\necho '__SHELL_READY__'\n")
        new_process.expect("__SHELL_READY__", timeout=10)
        session["process"] = new_process

    def execute(self, session_id: str, command: str, timeout: int = 300) -> tuple[int, str, str]:
        # 1. 自动检测并创建！
        self._ensure_shell(session_id)

        # 2. 获取锁定与会话
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
            full_payload = f"{command.strip()}\necho -e \"\\n{marker_str}$?|$(pwd)\""

            process.sendline(full_payload)

            try:
                process.expect(f"{marker_str}(\\d+)\\|(.*)", timeout=timeout)
            except pexpect.exceptions.TIMEOUT:
                partial_output = self._clean_ansi(process.before or "")
                print(f"[red]⚠️ Shell '{session_id}' timed out. Resetting...[/red]")
                self._restart_shell(session_id)
                return -1, f"⚠️ Command timed out after {timeout} seconds.\nPartial Output:\n{partial_output.strip()}", "unknown"

            exit_code = int(process.match.group(1))
            cwd = process.match.group(2).strip()

            raw_output = process.before
            cleaned_output = self._clean_ansi(raw_output).strip()
            lines = [line for line in cleaned_output.splitlines() if line.strip() != command.strip()]
            final_output = "\n".join(lines).strip()

            return exit_code, final_output, cwd

    def _clean_ansi(self, text: str) -> str:
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
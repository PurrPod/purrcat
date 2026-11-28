import atexit
import contextlib
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from typing import Optional

import docker
import pexpect
from docker.errors import DockerException, ImageNotFound, NotFound

from src.utils import sandbox_mounts
from src.utils.config import AGENT_VM_DIR, PURRCAT_DIR
from . import _shared
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
    import fcntl

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
    return _shared.build_exec_command(_resolve_docker_cmd(), container_name)


_docker_manager_instance: Optional["DockerManager"] = None

# 共享专属沙盒的容器名（start/stop 逻辑都以它为准）
SANDBOX_CONTAINER_NAME = "agent_computer"

# 容器运行参数版本：tmpfs 缓存挂载 / 缓存环境变量等变更后必须重建容器才会生效，
# 旧容器标签不匹配时自动销毁重建（工作目录是 bind mount，文件不受影响）
SANDBOX_ENV_REVISION = "2"
ENV_REVISION_LABEL = "purrcat.env_rev"

# 挂载变更时先把当前容器提交为快照镜像再重建，保留 pip/npm/apt 安装环境
STATE_IMAGE_REPO = "purrcat-sandbox"
STATE_IMAGE_TAG = "state"
STATE_IMAGE_REF = f"{STATE_IMAGE_REPO}:{STATE_IMAGE_TAG}"
FLAT_IMAGE_REF = f"{STATE_IMAGE_REPO}:flat"


def build_container_path(workspace: str, image_env: list[str] | None = None) -> str:
    """把持久工具目录拼到镜像自带 PATH 前面，容器内所有进程都可见。"""
    base = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    for item in image_env or []:
        if item.startswith("PATH="):
            base = item.split("=", 1)[1] or base
            break
    prefix = f"{workspace}/.env/bin:{workspace}/.env/npm/bin"
    if base == prefix or base.startswith(prefix + ":"):
        return base
    return f"{prefix}:{base}"


def build_import_changes(config: dict) -> list[str]:
    """export/import 压平时把镜像元数据补回去（CMD/ENTRYPOINT/ENV/WORKDIR/USER）。"""
    changes: list[str] = []
    cmd = config.get("Cmd") or ["sleep", "infinity"]
    changes += ["--change", f"CMD {json.dumps(cmd, ensure_ascii=False)}"]
    if config.get("Entrypoint"):
        changes += [
            "--change",
            f"ENTRYPOINT {json.dumps(config['Entrypoint'], ensure_ascii=False)}",
        ]
    for item in config.get("Env") or []:
        changes += ["--change", f"ENV {item}"]
    if config.get("WorkingDir"):
        changes += ["--change", f"WORKDIR {config['WorkingDir']}"]
    if config.get("User"):
        changes += ["--change", f"USER {config['User']}"]
    return changes


# 同进程内所有 DockerManager 实例共用一把可重入锁（Bash 工具与 API 可能并发）
_LIFECYCLE_LOCK = threading.RLock()
_MUTEX_KERNEL32 = None
_MUTEX_HANDLE = None


@contextlib.contextmanager
def _sandbox_file_lock():
    """跨进程互斥：API 进程应用挂载与 Bash 子进程启动/重建容器串行执行。"""
    global _MUTEX_KERNEL32, _MUTEX_HANDLE
    if sys.platform == "win32":
        # 命名互斥体由系统管理，进程崩溃会自动释放，比文件字节锁可靠
        if _MUTEX_KERNEL32 is None:
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            kernel32.CreateMutexW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_wchar_p,
            ]
            kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel32.WaitForSingleObject.restype = ctypes.c_uint32
            kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
            kernel32.ReleaseMutex.restype = ctypes.c_int
            _MUTEX_KERNEL32 = kernel32
        kernel32 = _MUTEX_KERNEL32
        if _MUTEX_HANDLE is None:
            _MUTEX_HANDLE = kernel32.CreateMutexW(
                None, False, "Local\\PurrcatSandboxLifecycle"
            )
        result = kernel32.WaitForSingleObject(_MUTEX_HANDLE, 600000)
        if result not in (0x0, 0x80):  # WAIT_OBJECT_0 / WAIT_ABANDONED
            raise RuntimeError("等待沙盒锁超时，请稍后重试")
        try:
            yield
        finally:
            kernel32.ReleaseMutex(_MUTEX_HANDLE)
        return

    lock_path = os.path.join(PURRCAT_DIR, "sandbox.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    handle = open(lock_path, "w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        handle.close()


def _stop_sandbox_on_exit():
    """主进程退出时把沙盒容器休眠（保留容器内的系统变更，进程不残留运行）。

    只能由真正的宿主（MainProcess）注册：bash 工具在子进程隔离下每次调用都会
    新建进程，若让子进程 atexit 去 stop 容器，会在其它并发会话的命令执行到一半时
    切断其 docker exec 连接，造成随机的 End Of File (EOF) 报错。
    """
    if _docker_manager_instance is None:
        # 本进程从未创建过沙盒（测试、纯 API 子命令），无需触碰 Docker
        return
    try:
        client = docker.from_env(timeout=5)
        container = client.containers.get(SANDBOX_CONTAINER_NAME)
        if container.status == "running":
            container.stop(timeout=2)
            print(f"[*] 宿主退出：沙盒 ({SANDBOX_CONTAINER_NAME}) 已休眠")
    except NotFound:
        # 容器已被手动删除或从未创建，属于正常状态
        pass
    except Exception as e:
        print(f"[*] 宿主退出时休眠沙盒失败(忽略): {e}")


if multiprocessing.current_process().name == "MainProcess":
    # 只有主进程注册退出清理；spawn 出来的 bash 子进程不应休眠共享容器
    atexit.register(_stop_sandbox_on_exit)


def _get_container_env() -> dict:
    # 既然主机开了 TUN 模式，容器不需要任何代理环境变量，直接跟主机共享网络上下文
    # 缓存目录统一指向 tmpfs（/tmp），避免 pip/npm/uv 的下载缓存写进容器可写层、
    # 把 docker 数据盘 vhdx 越撑越大（tmpfs 随容器停机释放）
    return _shared.container_env()


def _is_docker_conn_error(err: Exception) -> bool:
    """Docker 引擎重启/停止后，旧命名管道连接会以 WinError 232/109 或 broken pipe 断开。"""
    if getattr(err, "winerror", None) in (232, 109):
        return True
    if isinstance(err, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
        return True
    text = str(err).lower()
    return any(
        marker in text
        for marker in (
            "管道正在被关闭",
            "pipe is being closed",
            "broken pipe",
            "winerror 232",
            "winerror 109",
        )
    )


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
        print(f"使用容器引擎: {self.engine}")

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
        # 容器生命周期锁：start / 快照重建 / 挂载应用互斥，避免并发改写容器
        self._lifecycle_lock = _LIFECYCLE_LOCK
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
        return _shared.normalize_mount_path(p)

    def start(self):
        with self._lifecycle_lock, _sandbox_file_lock():
            self._start_with_recovery()

    def _reset_client(self):
        """引擎重启后旧管道连接已死，重建客户端并丢弃旧容器句柄。"""
        try:
            self.client = docker.from_env()
        except Exception as e:
            print(f"[!] 重新连接 Docker 失败: {e}")
        self.container = None
        self._started = False

    def _start_with_recovery(self):
        """启动遇到失效连接时自动重连重试，避免引擎重启后要手动再点一次。"""
        for attempt in range(3):
            try:
                self._start_locked()
                return
            except Exception as e:
                if not _is_docker_conn_error(e) or attempt == 2:
                    raise
                print(f"[!] Docker 连接已失效，重连后重试: {e}")
                self._reset_client()
                time.sleep(1)

    def _start_locked(self):
        if self._started and self.container is not None:
            try:
                self.container.reload()
                if self.container.status == "running":
                    self._ensure_env_dirs()
                    print(f"[*] 复用已有沙盒 ({self.container_name})，状态: running")
                    return
            except Exception:
                pass

        if self._started:
            print(f"[-] 沙盒 ({self.container_name}) 状态异常，尝试重启...")

        # ---------- 替换旧容器清理逻辑：唤醒休眠容器 ----------
        try:
            existing_container = self.client.containers.get(self.container_name)

            # 挂载校验：数据根目录变更后（换盘），旧容器的 /agent_vm
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
                        f"沙盒 ({self.container_name}) 挂载错位: 容器挂 {mount_src}，"
                        f"当前数据根要求 {want_src}，销毁重建..."
                    )
                    if existing_container.status == "running":
                        existing_container.stop(timeout=2)
                    existing_container.remove(force=True, v=True)
                    raise NotFound("mount mismatch, force recreate")

            # 运行参数版本校验：tmpfs 缓存挂载等改动只对新容器生效，
            # 旧容器不带标签会继续把缓存写进可写层（vhdx 持续膨胀）
            rev = (existing_container.labels or {}).get(ENV_REVISION_LABEL)
            if rev != SANDBOX_ENV_REVISION:
                print(
                    f"沙盒 ({self.container_name}) 运行参数版本 {rev or '未标注'} "
                    f"≠ 当前 {SANDBOX_ENV_REVISION}，销毁重建（工作目录文件不受影响）..."
                )
                if existing_container.status == "running":
                    existing_container.stop(timeout=2)
                existing_container.remove(force=True)
                raise NotFound("env revision mismatch, force recreate")

            if existing_container.status != "running":
                print(f"[-] 发现休眠沙盒 ({self.container_name})，正在唤醒...")
                existing_container.start()
            else:
                print(f"[*] 专属沙盒 ({self.container_name}) 已在运行。")

            self.container = existing_container
            self._started = True
            self._ensure_env_dirs()
            return  # 成功复用已有容器，直接返回，不再执行后面的 run 创建逻辑

        except NotFound:
            # 上次重建中途连接断开时，旧环境还在 _prev 里，优先恢复而不是新建空容器
            try:
                prev = self.client.containers.get(self.container_name + "_prev")
                print(f"[!] 发现上次重建中断的沙盒 ({prev.name})，正在恢复...")
                prev.rename(self.container_name)
                self.container = self.client.containers.get(self.container_name)
                if self.container.status != "running":
                    self.container.start()
                self._started = True
                self._ensure_env_dirs()
                return
            except Exception:
                pass
            print(
                f"未找到沙盒 ({self.container_name})，将基于镜像 {self.image} 创建全新虚拟机..."
            )
            pass  # 继续往下走原来的创建代码
        except DockerException as e:
            raise DockerNotRunningError(f"{self.engine.capitalize()} API 连接失败: {e}")

        env_vars = _get_container_env()

        try:
            print(f"正在基于镜像 {self.image} 创建全新沙盒...")
            self.container = self._run_container(self.image, self._build_volumes())
            self._ensure_env_dirs()
            self._prune_stale_mount_dirs()

            if env_vars.get("HTTP_PROXY"):
                proxy_url = env_vars["HTTP_PROXY"]
                print(f"检测到代理环境，正在为容器内部 apt 注入代理配置: {proxy_url}")
                apt_cmd = f'sh -c \'echo "Acquire::http::Proxy \\"{proxy_url}\\";\\nAcquire::https::Proxy \\"{proxy_url}\\";" > /etc/apt/apt.conf.d/99proxy\''
                self.container.exec_run(apt_cmd, user="root")

            self._run_setup_script()
            self._started = True
            print("全新沙盒环境启动就绪！")
        except ImageNotFound:
            raise DockerImageNotFoundError(f"找不到镜像: {self.image}")
        except DockerException as e:
            raise DockerImageNotFoundError(f"容器启动异常: {e}")

    def _ensure_env_dirs(self):
        """持久工具目录（/agent_vm/.env）随工作目录保留，重依赖放这里不进镜像层。"""
        if not self.workspace_dir:
            return
        for sub in (".env/bin", ".env/npm/bin", ".env/cache"):
            try:
                os.makedirs(
                    os.path.join(self.workspace_dir, *sub.split("/")), exist_ok=True
                )
            except Exception:
                pass

    def _prune_stale_mount_dirs(self):
        """清掉已移除挂载留下的空目录（挂载点上的 rmdir 会失败，不会误删）。"""
        if self.container is None:
            return
        try:
            self.container.exec_run(
                'sh -c \'for d in /mount/*; do [ -d "$d" ] && rmdir "$d" 2>/dev/null; done\''
            )
        except Exception:
            pass

    def _build_volumes(self, mounts: list[dict] | None = None) -> dict:
        """工作目录 + 用户挂载（/mount/<别名>）的 bind mount 表。"""
        volumes = {}
        if self.workspace_dir is not None:
            os.makedirs(self.workspace_dir, exist_ok=True)
            volumes[os.path.abspath(self.workspace_dir)] = {
                "bind": self.container_workspace,
                "mode": "rw",
            }
        for item in sandbox_mounts.container_mounts(mounts):
            volumes[os.path.abspath(item["source"])] = {
                "bind": item["destination"],
                "mode": "rw",
            }
        return volumes

    def _run_container(self, image_ref: str, volumes: dict):
        """按固定运行参数创建容器（首次创建与快照重建共用）。"""
        environment = _get_container_env()
        try:
            image_attrs = (self.client.images.get(image_ref).attrs or {}).get(
                "Config", {}
            )
            image_env = image_attrs.get("Env")
            image_volumes = list((image_attrs.get("Volumes") or {}).keys())
        except Exception:
            image_env = None
            image_volumes = []
        environment["PATH"] = build_container_path(self.container_workspace, image_env)
        # 临时目录挂 tmpfs：编译中间产物、下载包不会写进容器可写层，
        # 停机即释放，避免 docker 数据盘 vhdx 无限膨胀
        tmpfs = {
            "/tmp": "rw,exec,nosuid,nodev,size=2g,mode=1777",
            "/var/tmp": "rw,exec,nosuid,nodev,size=1g,mode=1777",
        }
        # 旧快照把挂载点记成了 VOLUME，重建时会生成无用匿名卷；用 tmpfs 占位
        bound = {v.get("bind") for v in volumes.values() if isinstance(v, dict)}
        for dest in image_volumes:
            if dest not in bound:
                tmpfs[dest] = "rw,size=1m,mode=1777"

        host_config = self.client.api.create_host_config(
            binds=volumes,
            port_bindings={
                "3000/tcp": ("0.0.0.0", 13000),
                "5173/tcp": ("0.0.0.0", 15173),
                "8080/tcp": ("0.0.0.0", 18080),
            },
            tmpfs=tmpfs,
            cap_add=["SYS_ADMIN"],
            security_opt=["seccomp=unconfined"],
            shm_size="2gb",
            extra_hosts={"host.docker.internal": "host-gateway"},
        )
        # 走低层 API 且不传 volumes，避免 Config.Volumes 被写入快照后变成 VOLUME
        created = self.client.api.create_container(
            image_ref,
            command="sleep infinity",
            name=self.container_name,
            detach=True,
            working_dir=self.container_workspace,
            environment=environment,
            labels={ENV_REVISION_LABEL: SANDBOX_ENV_REVISION},
            host_config=host_config,
        )
        self.client.api.start(created["Id"])
        return self.client.containers.get(created["Id"])

    def _run_container_with_retry(self, image_ref: str, volumes: dict):
        """新建容器偶发端口释放延迟时重试，避免旧容器刚停下就绑定失败。"""
        last_error = RuntimeError("沙盒容器创建失败")
        for attempt in range(3):
            try:
                return self._run_container(image_ref, volumes)
            except Exception as e:
                last_error = e
                self._remove_container_if_exists(self.container_name)
                if attempt < 2:
                    time.sleep(1)
        raise last_error

    def _run_setup_script(self):
        """重建容器后执行工作目录里的 .agent_env/setup.sh

        容器可写层随重建丢失（apt/pip 装过的依赖没了），用户可以在
        <工作目录>/.agent_env/setup.sh 里写恢复脚本，重建后自动执行一次。
        """
        if self.workspace_dir is None:
            return
        host_path = os.path.join(self.workspace_dir, ".agent_env", "setup.sh")
        if not os.path.isfile(host_path):
            return
        print(
            f"[*] 发现 {host_path}，重建后自动执行以恢复容器环境（可能需要几分钟）..."
        )
        try:
            exit_code, output = self.container.exec_run(
                ["bash", f"{self.container_workspace}/.agent_env/setup.sh"],
                workdir=self.container_workspace,
                demux=False,
            )
            text = (output or b"").decode("utf-8", "replace").strip()
            if text:
                print(text[-2000:])
            print(f"[{'*' if exit_code == 0 else '!'}] setup.sh 退出码: {exit_code}")
        except Exception as e:
            print(f"[!] setup.sh 执行失败(忽略): {e}")

    def stop(self):
        with self._lifecycle_lock, _sandbox_file_lock():
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

    def _state_image_id(self) -> str | None:
        try:
            return self.client.images.get(STATE_IMAGE_REF).id
        except Exception:
            return None

    def _mounted_paths(self) -> dict[str, str]:
        """当前容器 /mount/* 的 {容器路径: 宿主路径}。"""
        result: dict[str, str] = {}
        if self.container is None:
            return result
        try:
            self.container.reload()
            for mount in self.container.attrs.get("Mounts") or []:
                # 只看 bind：commit 会把挂载点写成 VOLUME，重建时会变成匿名卷，
                # 那不是真实挂载，不能参与匹配
                if str(mount.get("Type") or "") != "bind":
                    continue
                destination = str(mount.get("Destination") or "")
                if destination.startswith(sandbox_mounts.CONTAINER_MOUNT_ROOT + "/"):
                    result[destination] = str(mount.get("Source") or "")
        except Exception:
            pass
        return result

    def _mounts_match(self, desired: list[dict], actual: dict[str, str]) -> bool:
        if len(desired) != len(actual):
            return False
        for item in desired:
            source = actual.get(item["destination"])
            if source is None or self._norm_mount_path(source) != self._norm_mount_path(
                item["source"]
            ):
                return False
        return True

    def _close_all_shells(self):
        with self.pool_lock:
            session_ids = list(self.shell_pool.keys())
        for session_id in session_ids:
            try:
                self.close_shell(session_id)
            except Exception:
                pass

    def _remove_container_if_exists(self, name: str):
        try:
            container = self.client.containers.get(name)
        except NotFound:
            return
        except Exception:
            return
        try:
            if container.status == "running":
                container.stop(timeout=2)
            container.remove(force=True, v=True)
        except Exception as e:
            print(f"[!] 清理容器 {name} 失败(忽略): {e}")

    def _preflight_mounts(self, desired: list[dict]):
        """提交快照前先用一次性容器验证宿主目录确实可被 Docker 挂载。"""
        if not desired or self.container is None:
            return
        volumes = {
            os.path.abspath(item["source"]): {
                "bind": item["destination"],
                "mode": "rw",
            }
            for item in desired
        }
        try:
            self.client.containers.run(
                self.container.image.id,
                command="true",
                remove=True,
                detach=False,
                volumes=volumes,
            )
        except Exception as e:
            raise RuntimeError(
                f"挂载目录无法被 Docker 访问，请检查 Docker Desktop 的文件共享设置: {e}"
            ) from e

    def _recreate_with_mounts(self, desired: list[dict]):
        """commit 当前容器用快照镜像 + 新挂载重建，失败回滚旧容器。"""
        old = self.container
        if old is None:
            try:
                old = self.client.containers.get(self.container_name)
            except NotFound as e:
                raise RuntimeError("沙盒尚未创建，无法应用挂载") from e
        old.reload()
        self._close_all_shells()
        self._preflight_mounts(desired)

        # 上次重建后容器文件系统没变化时，跳过快照，直接用当前镜像重建，避免空层
        try:
            changed = bool(old.diff())
        except Exception:
            changed = True
        snapshot = None
        previous_state_id = None
        if changed:
            previous_state_id = self._state_image_id()
            try:
                snapshot = old.commit(
                    repository=STATE_IMAGE_REPO, tag=STATE_IMAGE_TAG, pause=True
                )
            except Exception as e:
                raise RuntimeError(f"沙盒环境快照失败，已取消挂载变更: {e}") from e
        else:
            print("[*] 容器文件系统无变化，跳过环境快照")

        if old.status == "running":
            old.stop(timeout=3)

        self._remove_container_if_exists(self.container_name + "_prev")
        old.rename(self.container_name + "_prev")
        try:
            new_container = self._run_container_with_retry(
                snapshot.id if snapshot else old.image.id,
                self._build_volumes(desired),
            )
        except Exception as e:
            # 新容器创建失败：清理残留并重启旧容器，避免沙盒不可用
            print(f"[!] 挂载重建失败，正在回滚旧容器: {e}")
            self._remove_container_if_exists(self.container_name)
            old.rename(self.container_name)
            old.start()
            self.container = old
            self._started = True
            raise

        self.container = new_container
        self._started = True
        self._prune_stale_mount_dirs()
        self._remove_container_if_exists(self.container_name + "_prev")
        if snapshot and previous_state_id and previous_state_id != snapshot.id:
            try:
                self.client.images.remove(previous_state_id, force=True)
            except Exception:
                pass
        print("[*] 沙盒已按挂载配置重建，容器内已安装环境已保留")

    def apply_mounts(self) -> dict:
        """把当前挂载配置应用到沙盒（必要时快照重建）。"""
        with self._lifecycle_lock, _sandbox_file_lock():
            configured = sandbox_mounts.load_mounts()
            missing = [
                item["name"] for item in configured if not os.path.isdir(item["source"])
            ]
            if missing:
                raise RuntimeError("以下挂载源不存在，无法应用：" + "、".join(missing))

            self._start_with_recovery()
            desired = sandbox_mounts.container_mounts(configured)
            if not self._mounts_match(desired, self._mounted_paths()):
                print("[*] 应用挂载配置：正在快照重建沙盒（容器环境保留）...")
                self._recreate_with_mounts(desired)
            if not self._mounts_match(desired, self._mounted_paths()):
                raise RuntimeError("沙盒挂载未能应用，请检查 Docker 与挂载源")
            return {"status": "ok", "mounts": desired}

    def flatten_sandbox(self, log=print) -> dict:
        """把容器文件系统压成单层镜像并重建（export/import，自动回填元数据）。"""
        with self._lifecycle_lock, _sandbox_file_lock():
            self._start_with_recovery()
            return self._flatten_locked(log)

    def _flatten_locked(self, log):
        old = self.container
        if old is None:
            raise RuntimeError("沙盒尚未创建")
        self._close_all_shells()
        changes = build_import_changes((old.image.attrs or {}).get("Config") or {})
        previous_state_id = self._state_image_id()

        fd, tar_path = tempfile.mkstemp(prefix="purrcat-flatten-", suffix=".tar")
        os.close(fd)
        try:
            if old.status == "running":
                old.stop(timeout=3)
            log("[*] 正在导出容器文件系统...")
            subprocess.run(
                [self.engine, "export", "-o", tar_path, self.container_name],
                check=True,
                capture_output=True,
            )
            size_mb = os.path.getsize(tar_path) / 1024 / 1024
            log(f"[*] 导出完成（{size_mb:.0f} MB），正在导入为单层镜像...")
            subprocess.run(
                [self.engine, "import", *changes, tar_path, FLAT_IMAGE_REF],
                check=True,
                capture_output=True,
            )
        except Exception as e:
            try:
                old.start()
            except Exception:
                pass
            if isinstance(e, subprocess.CalledProcessError):
                err = (e.stderr or b"").decode("utf-8", "ignore").strip()
                raise RuntimeError(f"export/import 失败: {err or e}") from e
            raise
        finally:
            try:
                os.remove(tar_path)
            except OSError:
                pass

        self._remove_container_if_exists(self.container_name + "_prev")
        old.rename(self.container_name + "_prev")
        try:
            new_container = self._run_container_with_retry(
                FLAT_IMAGE_REF, self._build_volumes()
            )
        except Exception as e:
            log(f"[!] 压缩后重建失败，正在回滚: {e}")
            self._remove_container_if_exists(self.container_name)
            try:
                self.client.images.remove(FLAT_IMAGE_REF, force=True)
            except Exception:
                pass
            old.rename(self.container_name)
            old.start()
            self.container = old
            self._started = True
            raise

        self.container = new_container
        self._started = True
        self._prune_stale_mount_dirs()
        self._remove_container_if_exists(self.container_name + "_prev")
        try:
            self.client.images.get(FLAT_IMAGE_REF).tag(
                STATE_IMAGE_REPO, STATE_IMAGE_TAG
            )
            self.client.images.remove(FLAT_IMAGE_REF)
        except Exception as e:
            log(f"[!] 更新快照标签失败(忽略): {e}")
        if previous_state_id:
            try:
                self.client.images.remove(previous_state_id, force=True)
            except Exception:
                pass
        log("[+] 沙盒镜像已压平为单层")
        return {"status": "ok"}

    def _container_has_persistent_path(self) -> bool:
        """容器启动环境里是否已包含 /agent_vm/.env 的 PATH（新容器为 True）。"""
        try:
            env = (self.container.attrs or {}).get("Config", {}).get("Env") or []
        except Exception:
            return False
        prefix = f"PATH={self.container_workspace}/.env/bin"
        return any(item.startswith(prefix) for item in env)

    def _spawn_shell_process(self):
        """创建一条新的 docker exec bash 会话，并完成就绪握手。"""
        command = _get_container_exec_cmd(self.container.name)
        shell_process = None
        try:
            shell_process = SpawnClass(command, encoding="utf-8", timeout=120)
            env_root = f"{self.container_workspace}/.env"
            path_line = ""
            if not self._container_has_persistent_path():
                # 旧容器创建时未注入 PATH，仅在它的会话里补一次兜底
                path_line = f"export PATH={env_root}/bin:{env_root}/npm/bin:$PATH\n"
            shell_process.send(
                "stty -echo\nexport PS1=''\nexport TERM=dumb\n"
                f"{path_line}"
                "echo '__SHELL_READY__'\n"
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
                full_payload = _shared.build_shell_payload(safe_command, marker_str)

                process.send(full_payload.replace("\r", "") + "\n")
                try:
                    process.expect(f"{marker_str}(\\d+)\\|(.*)", timeout=timeout)
                    break
                except pexpect.exceptions.TIMEOUT:
                    partial_output = self._clean_ansi(process.before or "")
                    print(f"[red]Shell '{session_id}' timed out. Resetting...[/red]")
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
                        f"[yellow]Shell '{session_id}' 会话断开(EOF)，"
                        "正在重启会话并重试命令...[/yellow]"
                    )
                    self._restart_shell(session_id)
                    process = session["process"]

            exit_code = int(process.match.group(1))
            cwd = process.match.group(2).strip()
            cleaned_output = self._clean_ansi(process.before).strip()
            final_output = _shared.strip_command_echo(cleaned_output, command)
            return exit_code, final_output, cwd

    def _clean_ansi(self, text: str) -> str:
        return _shared.clean_ansi(text)


def get_docker_manager() -> "DockerManager":
    global _docker_manager_instance
    if _docker_manager_instance is None:
        _docker_manager_instance = DockerManager(
            image="my_agent_env:latest", workspace_dir=AGENT_VM_DIR
        )
        # 注意：不再在此处注册 atexit 休眠容器。bash 工具在子进程隔离下每次
        # 调用都会新建进程，若每个子进程退出时都 stop 共享容器，会切断其它并发
        # 会话正在执行的 docker exec 连接随机 End Of File (EOF)。
        # 容器休眠统一由模块顶部 MainProcess 的退出钩子负责。

    _docker_manager_instance.start()
    return _docker_manager_instance

"""磁盘维护的写操作：容器重建、停启 Docker、vhdx 压缩、构建缓存清理。"""

import os
import subprocess
import tempfile
import time

from src.utils._proc import find_docker_desktop_exe, run_text, subprocess_encoding
from src.utils.config import get_enriched_env, save_global_setting
from src.utils.disk_metrics import SANDBOX_CONTAINER
from src.utils.disk_probe import (
    docker_cli,
    docker_running,
    reset_live_cache,
    reset_run_cache,
    reset_sandbox_cache,
)


def run_command(cmd: list, log, timeout: float = 120) -> int:
    try:
        r = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            encoding=subprocess_encoding(),
            errors="replace",
            env=get_enriched_env(),
        )
        out = (r.stdout or "").strip()
        if out:
            for line in out.splitlines()[-20:]:
                log("    " + line)
        return r.returncode
    except subprocess.TimeoutExpired:
        log(f"[!] 命令超时（{int(timeout)}s）: {' '.join(cmd[:3])}")
        return -1
    except Exception as e:
        log(f"[!] 命令执行失败: {cmd[0]}: {e}")
        return -1


def rebuild_sandbox() -> tuple[bool, str]:
    """删除沙盒容器（可写层随容器销毁，bind mount 的工作目录不受影响）。

    下次工具调用时 DockerManager.start() 会自动基于镜像重建，
    这是清理容器内累积的 apt/pip 安装与缓存的唯一彻底办法。
    """
    docker = docker_cli()
    if not docker:
        return False, "未检测到 docker 命令"
    if not docker_running(docker):
        return False, "Docker 未运行，无法重建容器"
    try:
        r = run_text(
            [docker, "rm", "-f", SANDBOX_CONTAINER],
            timeout=120,
        )
    except Exception as e:
        return False, f"删除容器失败: {e}"
    reset_sandbox_cache()
    if r.returncode != 0:
        out = (r.stderr or r.stdout or "").strip()
        if "No such container" in out:
            return True, "沙盒容器不存在，无需重建"
        return False, out or "删除容器失败"
    return True, "沙盒容器已删除，下次工具调用会自动重建（工作目录文件不受影响）"


def stop_docker(log) -> None:
    """停掉沙盒容器与 Docker Desktop，并关停 WSL 以释放 vhdx 文件句柄"""
    docker = docker_cli()
    if docker:
        log("[*] 休眠沙盒容器 ...")
        run_command([docker, "stop", SANDBOX_CONTAINER], log, timeout=60)

        log("[*] 停止 Docker Desktop ...")
        if run_command([docker, "desktop", "stop"], log, timeout=180) != 0:
            log("[*] 当前 Docker 版本不支持 desktop stop，改用进程退出")
            run_command(
                ["taskkill", "/IM", "Docker Desktop.exe", "/F"], log, timeout=30
            )

    log("[*] 关闭 WSL 虚拟机 ...")
    run_command(["wsl", "--shutdown"], log, timeout=120)

    deadline = time.time() + 60
    while time.time() < deadline:
        if not docker_running(docker):
            break
        time.sleep(3)
    reset_run_cache()
    time.sleep(3)  # 等文件句柄真正释放


def compact_vhdx(vhdx: str) -> tuple[bool, str]:
    """提权执行 diskpart compact（一次 UAC 授权），返回 (成功, 说明)"""
    script = "\r\n".join(
        [
            f'select vdisk file="{vhdx}"',
            "attach vdisk readonly",
            "compact vdisk",
            "detach vdisk",
            "exit",
        ]
    )
    fd, script_path = tempfile.mkstemp(prefix="purrcat_compact_", suffix=".txt")
    try:
        # diskpart 按系统 ANSI 代码页读取脚本（中文系统 = GBK），用 UTF-8 会乱码
        try:
            data = script.encode("mbcs")
        except Exception:
            data = script.encode("utf-8")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        esc_path = script_path.replace("'", "''")
        ps = (
            "$ErrorActionPreference='Stop'; "
            "$p = Start-Process -FilePath diskpart.exe "
            f"-ArgumentList '/s','{esc_path}' "
            "-Verb RunAs -Wait -PassThru; exit $p.ExitCode"
        )
        r = run_text(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            timeout=1800,
        )
        err = (r.stderr or "").strip()
        if r.returncode != 0:
            if "canceled" in err.lower() or "取消" in err:
                return False, "已取消管理员授权（UAC），未执行压缩"
            return False, err or f"diskpart 退出码 {r.returncode}"
        return True, "diskpart 压缩完成"
    except subprocess.TimeoutExpired:
        return False, "diskpart 压缩超时"
    except Exception as e:
        return False, f"压缩失败: {e}"
    finally:
        try:
            os.remove(script_path)
        except Exception:
            pass


def start_docker(log) -> None:
    exe = find_docker_desktop_exe()
    if not exe:
        log("[!] 未找到 Docker Desktop，压缩完成后请手动启动 Docker")
        return
    log("[*] 重新启动 Docker Desktop ...")
    try:
        subprocess.Popen([exe], close_fds=True)
    except Exception as e:
        log(f"[!] 启动 Docker Desktop 失败: {e}")
        return
    docker = docker_cli()
    deadline = time.time() + 180
    while time.time() < deadline:
        if docker_running(docker):
            log("[+] Docker 已恢复运行")
            return
        time.sleep(5)
    log("[!] Docker 启动等待超时，请手动检查（容器会在下次工具调用时自动拉起）")


def prune_build_cache(log) -> bool:
    docker = docker_cli()
    if not docker or not docker_running(docker):
        log("[!] Docker 未运行，跳过构建缓存清理")
        return False
    log("[*] 清理构建缓存: docker builder prune -af ...")
    code = run_command([docker, "builder", "prune", "-af"], log, timeout=600)
    if code != 0:
        log(f"[!] 构建缓存清理失败（退出码 {code}）")
        return False
    save_global_setting("docker_prune_at", time.time())
    reset_live_cache()
    log("[+] 构建缓存已清理")
    return True

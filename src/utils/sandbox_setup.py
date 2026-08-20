"""
沙盒镜像自动检测与获取（仅支持 Docker，已移除 Podman）
启动时检查：
  1. docker CLI 是否存在
  2. docker daemon 是否运行
  3. my_agent_env:latest 镜像是否存在
缺则后台线程自动从 ghcr.io 拉取 light 镜像（轻量、最快可用）
都不行 → 打印引导，不阻塞、不崩溃
"""

import subprocess
import sys
import threading

from src.utils.config import BASE_DIR

SANDBOX_IMAGE_TAG = "my_agent_env:latest"
GHCR_LIGHT_IMAGE = "ghcr.io/purrpod/purrcat-sandbox:light"
DOCKER_NOT_FOUND_HINT = (
    "[*] 未检测到 Docker。沙盒功能（Bash 执行）将不可用。\n"
    "    安装指引: https://docs.docker.com/get-docker/\n"
    "    Windows 推荐 Docker Desktop（需要启用 WSL2），安装后重启系统。"
)
DOCKER_DAEMON_HINT = (
    "[*] 检测到 Docker CLI，但 daemon 未启动。\n"
    "    请先启动 Docker Desktop / dockerd，然后重试。"
)

_sandbox_lock = threading.Lock()
_sandbox_running = threading.Event()


def docker_cmd() -> str | None:
    """返回解析后的 docker 命令绝对路径，找不到返回 None"""
    import shutil

    return shutil.which("docker")


def check_docker_running(docker: str) -> bool:
    try:
        result = subprocess.run(
            [docker, "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def check_image_exists(docker: str, tag: str) -> bool:
    try:
        result = subprocess.run(
            [docker, "image", "inspect", tag],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except Exception:
        return False


def _print_stream(process: subprocess.Popen, prefix: str):
    for line in process.stdout:
        print(f"{prefix}{line}", end="")


def _pull_light_image(docker: str) -> bool:
    """从 ghcr.io 拉取 light 版沙盒并 retag"""
    print(f"[*] 未检测到沙盒镜像，正在后台拉取 {GHCR_LIGHT_IMAGE} ...")
    print("    首次下载可能需要几分钟，取决于网络。")
    print("    进度可观察上方 docker pull 输出。")

    encoding = "gbk" if sys.platform == "win32" else "utf-8"
    pull = subprocess.Popen(
        [docker, "pull", GHCR_LIGHT_IMAGE],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=encoding,
        errors="replace",
        bufsize=1,
    )
    _print_stream(pull, "    ")
    pull.wait()
    if pull.returncode != 0:
        return False

    tag = subprocess.Popen(
        [docker, "tag", GHCR_LIGHT_IMAGE, SANDBOX_IMAGE_TAG],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=encoding,
        errors="replace",
        bufsize=1,
    )
    _print_stream(tag, "    ")
    tag.wait()
    return tag.returncode == 0


def ensure_sandbox_image() -> None:
    """
    启动时检查 Docker + 沙盒镜像。
    - 无 Docker：打印引导，返回（不报错、不阻塞）
    - 有 Docker 但无镜像：后台线程自动拉取 light 版
    - 有 Docker 且有镜像：直接跳过
    """
    docker = docker_cmd()

    # 1) 连 docker CLI 都没有 — 静默引导用户安装
    if not docker:
        print("")
        print(DOCKER_NOT_FOUND_HINT)
        print("")
        return

    # 2) daemon 未启动
    if not check_docker_running(docker):
        print("")
        print(DOCKER_DAEMON_HINT)
        print("")
        return

    # 3) 镜像已存在，跳过
    if check_image_exists(docker, SANDBOX_IMAGE_TAG):
        return

    if _sandbox_running.is_set():
        return

    with _sandbox_lock:
        if _sandbox_running.is_set():
            return
        _sandbox_running.set()

    def _do_pull():
        try:
            ok = _pull_light_image(docker)
            if ok:
                print(f"[+] 沙盒镜像已就绪: {SANDBOX_IMAGE_TAG}")
            else:
                print("[!] 沙盒镜像拉取失败。")
                print(
                    "    可手动执行: docker pull ghcr.io/purrpod/purrcat-sandbox:light"
                )
                print(
                    "    或通过: purrcat setup （支持选择 full 镜像、国内镜像源、本地 build）"
                )
        except Exception as e:
            print(f"[!] 沙盒镜像下载异常: {e}")
        finally:
            _sandbox_running.clear()

    threading.Thread(target=_do_pull, daemon=True).start()


# ========================================================
# 以下函数仅供 purrcat setup 命令（带交互）复用
# ========================================================


def interactive_build_sandbox(
    variant: str = "light",
    apt_mirror: str = "deb.debian.org",
    source: str = "pull",
) -> bool:
    """
    交互 setup 调用的沙盒构建函数。
    variant: "light" | "full"
    apt_mirror: deb.debian.org | mirrors.aliyun.com
    source: "pull" | "build"
    """
    docker = docker_cmd()
    if not docker:
        print(DOCKER_NOT_FOUND_HINT)
        return False

    if not check_docker_running(docker):
        print(DOCKER_DAEMON_HINT)
        return False

    ghcr_image = f"ghcr.io/purrpod/purrcat-sandbox:{variant}"
    dockerfile = f"Dockerfile.{variant}"

    if source == "pull":
        print(f"Pulling sandbox image from {ghcr_image} ...")
        success = (
            subprocess.call(
                [docker, "pull", ghcr_image],
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            == 0
        )
        if not success:
            print("Pull failed.")
            return False
        success = (
            subprocess.call(
                [docker, "tag", ghcr_image, SANDBOX_IMAGE_TAG],
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            == 0
        )
        if success:
            print(f"Tagged as {SANDBOX_IMAGE_TAG}")
        return success
    else:
        print(f"Building sandbox using {dockerfile} (APT mirror: {apt_mirror}) ...")
        build_cmd = [
            docker,
            "build",
            "-f",
            dockerfile,
            "-t",
            SANDBOX_IMAGE_TAG,
            "--build-arg",
            f"APT_MIRROR={apt_mirror}",
            ".",
        ]
        return subprocess.call(build_cmd, cwd=BASE_DIR) == 0

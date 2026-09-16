"""
沙盒镜像自动检测与获取（仅支持 Docker，已移除 Podman）
启动时检查：
  1. docker CLI 是否存在
  2. docker daemon 是否运行
  3. my_agent_env:latest 镜像是否存在
缺则后台线程多源依次拉取（自定义源 → ghcr.io → 公共代理，失败自动换源）
都不行 → 打印引导，不阻塞、不崩溃
"""

import subprocess
import sys
import threading

SANDBOX_IMAGE_TAG = "my_agent_env:latest"
IMAGE_TAG = "purrcat-sandbox:light"

# 拉取源：依次尝试。ghcr.io 为官方源排最前；国内直连不稳时走南大镜像站；
# Docker Hub 排最后兜底——只有配置了镜像加速器的用户能吃到（加速器不代理 ghcr），
# 未配加速器的国内用户直连 docker.io 基本连不上（DaoCloud 公共代理已匿名 DENIED，不可用）
SANDBOX_IMAGE_SOURCES = [
    f"ghcr.io/purrpod/{IMAGE_TAG}",
    f"ghcr.nju.edu.cn/purrpod/{IMAGE_TAG}",
    f"docker.io/sukice/{IMAGE_TAG}",
]
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


def _custom_sources() -> list:
    """settings.json 的 sandbox_registry：registry 前缀（如 ghcr.m.daocloud.io）"""
    try:
        from src.utils.config import get_global_settings

        value = (
            str(get_global_settings().get("sandbox_registry") or "").strip().rstrip("/")
        )
    except Exception:
        return []
    return [f"{value}/{IMAGE_TAG}"] if value else []


def _candidate_sources() -> list:
    seen, sources = set(), []
    for image in _custom_sources() + SANDBOX_IMAGE_SOURCES:
        if image not in seen:
            seen.add(image)
            sources.append(image)
    return sources


def _run_and_log(cmd: list, log, timeout: float | None = None) -> int:
    """执行 docker 命令，输出逐行交给 log；返回退出码（超时/异常返回 -1）"""
    encoding = "gbk" if sys.platform == "win32" else "utf-8"
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=encoding,
            errors="replace",
            bufsize=1,
        )
    except Exception as e:
        log(f"[!] 启动命令失败: {cmd[0]}: {e}")
        return -1

    def _pump():
        try:
            for line in proc.stdout:
                log(line.rstrip())
        except Exception:
            pass

    reader = threading.Thread(target=_pump, daemon=True)
    reader.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        log(f"[!] 超时（{int(timeout)}秒），已终止")
        return -1
    reader.join(timeout=5)
    return proc.returncode


def pull_sandbox_image(docker: str, log=print, timeout: float | None = None) -> bool:
    """按候选源顺序拉取沙盒镜像并 retag 为 SANDBOX_IMAGE_TAG；全部失败返回 False"""
    sources = _candidate_sources()
    for i, image in enumerate(sources, 1):
        log(f"[*] 拉取沙盒镜像（{i}/{len(sources)}）: {image}")
        code = _run_and_log([docker, "pull", image], log, timeout)
        if code != 0:
            log(f"[!] {image} 拉取失败，尝试下一个源...")
            continue
        code = _run_and_log([docker, "tag", image, SANDBOX_IMAGE_TAG], log, 60)
        if code == 0:
            return True
        log("[!] 镜像打标签失败")
    return False


def ensure_sandbox_image() -> None:
    """
    启动时检查 Docker + 沙盒镜像。
    - 无 Docker：打印引导，返回（不报错、不阻塞）
    - 有 Docker 但无镜像：后台线程多源拉取
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
            print("[*] 未检测到沙盒镜像，后台开始多源拉取...")
            print("    首次下载可能需要几分钟，取决于网络。")
            ok = pull_sandbox_image(docker)
            if ok:
                print(f"[+] 沙盒镜像已就绪: {SANDBOX_IMAGE_TAG}")
            else:
                print("[!] 所有镜像源均拉取失败。")
                print(
                    "    可在 配置中心 → 部署 → 镜像源 设置自定义源后重试，"
                    "或手动拉取任一源后执行 docker tag <镜像> my_agent_env:latest"
                )
        except Exception as e:
            print(f"[!] 沙盒镜像下载异常: {e}")
        finally:
            _sandbox_running.clear()

    threading.Thread(target=_do_pull, daemon=True).start()

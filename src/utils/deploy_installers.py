"""部署项的安装命令构造与执行。

纯函数只负责拼命令（便于单测）；执行路径与原实现保持一致：
Windows 走 powershell / winget，macOS 走 Homebrew，Linux 走免密 sudo。
"""

import subprocess
import sys
import time

from src.utils._proc import find_docker_desktop_exe, run_stream
from src.utils.config import get_enriched_env
from src.utils.deploy_tasks import append_log
from src.utils.deploy_probe import quick_version, which_enriched

_WIN = sys.platform.startswith("win")
_MAC = sys.platform == "darwin"


# ══════════════ 纯命令构造 ══════════════


def uv_install_command(platform: str | None = None) -> list:
    platform = platform or sys.platform
    if platform.startswith("win"):
        return [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "irm https://astral.sh/uv/install.ps1 | iex",
        ]
    return ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]


def node_winget_command(winget: str) -> list:
    return [
        winget,
        "install",
        "--id",
        "OpenJS.NodeJS.LTS",
        "-e",
        "--accept-source-agreements",
        "--accept-package-agreements",
    ]


def node_brew_command(brew: str) -> list:
    return [brew, "install", "node"]


def node_linux_candidates() -> list:
    return [
        ("apt-get", ["sudo", "-n", "apt-get", "install", "-y", "nodejs", "npm"]),
        ("dnf", ["sudo", "-n", "dnf", "install", "-y", "nodejs", "npm"]),
        ("yum", ["sudo", "-n", "yum", "install", "-y", "nodejs", "npm"]),
        ("pacman", ["sudo", "-n", "pacman", "-S", "--noconfirm", "nodejs", "npm"]),
    ]


def docker_desktop_winget_command(winget: str) -> list:
    return [
        winget,
        "install",
        "--id",
        "Docker.DockerDesktop",
        "-e",
        "--accept-source-agreements",
        "--accept-package-agreements",
    ]


def docker_desktop_brew_command(brew: str) -> list:
    return [brew, "install", "--cask", "docker"]


def docker_linux_install_command() -> list:
    return ["sh", "-c", "curl -fsSL https://get.docker.com | sudo -n sh"]


# ══════════════ 执行包装 ══════════════


def _run_stream(item: str, cmd: list, timeout: float | None = None) -> int:
    return run_stream(
        cmd,
        lambda line: append_log(item, line),
        timeout,
        env=get_enriched_env(),
    )


# ══════════════ 安装实现 ══════════════


def install_uv(item: str) -> bool:
    append_log(item, "[*] 通过官方安装脚本安装 uv ...")
    code = _run_stream(item, uv_install_command(), timeout=600)
    if code != 0:
        append_log(item, "[!] uv 安装脚本执行失败，请检查网络后重试")
        return False
    if not which_enriched("uv"):
        append_log(item, "[!] 脚本已执行但未找到 uv 命令，请重启程序后重试")
        return False
    append_log(item, f"[+] uv 安装成功: {which_enriched('uv')}")
    return True


def install_node(item: str) -> bool:
    if _WIN:
        winget = which_enriched("winget")
        if not winget:
            append_log(
                item, "[!] 未检测到 winget，请手动安装 Node.js: https://nodejs.org/"
            )
            return False
        append_log(
            item, "[*] 通过 winget 安装 Node.js LTS（安装包较大，请耐心等待）..."
        )
        code = _run_stream(item, node_winget_command(winget), timeout=1800)
        if code != 0:
            append_log(item, "[!] winget 安装失败，可手动安装: https://nodejs.org/")
            return False
    elif _MAC:
        brew = which_enriched("brew")
        if not brew:
            append_log(
                item, "[!] 未检测到 Homebrew，请手动安装 Node.js: https://nodejs.org/"
            )
            return False
        append_log(item, "[*] 通过 Homebrew 安装 Node.js ...")
        code = _run_stream(item, node_brew_command(brew), timeout=1800)
        if code != 0:
            append_log(item, "[!] brew install node 失败")
            return False
    else:
        # Linux：逐个尝试发行版包管理器（sudo 免密场景可直接装，否则给出手动指引）
        for mgr, cmd in node_linux_candidates():
            if not which_enriched(mgr):
                continue
            append_log(item, f"[*] 通过 {mgr} 安装 Node.js（需要 sudo 免密授权）...")
            if _run_stream(item, cmd, timeout=1800) == 0 and which_enriched("node"):
                break
            append_log(item, f"[!] {mgr} 安装失败，尝试下一种方式")
        else:
            append_log(item, "[!] 自动安装失败。请手动安装 Node.js，例如：")
            append_log(item, "    sudo apt-get install -y nodejs npm   # Debian/Ubuntu")
            append_log(item, "    或参考 https://nodejs.org/en/download")
            return False
    if not which_enriched("node"):
        append_log(item, "[!] 安装完成但未找到 node 命令，请重启程序后重试")
        return False
    append_log(
        item,
        f"[+] Node.js 安装成功: {quick_version([which_enriched('node'), '--version'])}",
    )
    return True


def _try_start_docker(item: str) -> None:
    """尝试拉起 Docker Desktop / dockerd（拉不起就等超时由调用方兜底）"""
    if _WIN:
        exe = find_docker_desktop_exe()
        if not exe:
            append_log(item, "[!] 未找到 Docker Desktop，请手动启动")
            return
        try:
            subprocess.Popen([exe], close_fds=True)
            append_log(item, f"[*] 已启动 Docker Desktop: {exe}")
        except Exception as e:
            append_log(item, f"[!] 启动 Docker Desktop 失败: {e}")
    elif _MAC:
        _run_stream(item, ["open", "-a", "Docker"], timeout=30)
    else:
        # 后台无 TTY，sudo 必须免密（-n），否则立即失败让调用方给出指引
        _run_stream(item, ["sudo", "-n", "systemctl", "start", "docker"], timeout=60)


def _wait_docker(docker: str, timeout: float) -> bool:
    from src.utils.sandbox_setup import check_docker_running

    deadline = time.time() + timeout
    while time.time() < deadline:
        if check_docker_running(docker):
            return True
        time.sleep(5)
    return check_docker_running(docker)


def install_sandbox(item: str) -> bool:
    from src.utils.sandbox_setup import (
        SANDBOX_IMAGE_TAG,
        check_docker_running,
        check_image_exists,
        pull_sandbox_image,
    )

    docker = which_enriched("docker")

    # 1) 无 Docker CLI → 安装 Docker Desktop
    if not docker:
        if _WIN:
            winget = which_enriched("winget")
            if not winget:
                append_log(
                    item,
                    "[!] 未检测到 winget，请手动安装 Docker Desktop: https://docs.docker.com/desktop/",
                )
                return False
            append_log(
                item, "[*] 通过 winget 安装 Docker Desktop（体积大，耗时较长）..."
            )
            code = _run_stream(
                item, docker_desktop_winget_command(winget), timeout=3600
            )
            if code != 0:
                append_log(
                    item,
                    "[!] Docker Desktop 安装失败，可手动安装: https://docs.docker.com/desktop/",
                )
                return False
            docker = which_enriched("docker")
            if not docker:
                append_log(
                    item,
                    "[!] Docker 已安装但当前会话找不到命令，请重启程序后再点一键部署",
                )
                return False
        elif _MAC:
            brew = which_enriched("brew")
            if not brew:
                append_log(
                    item,
                    "[!] 未检测到 Homebrew，请手动安装 Docker Desktop: https://docs.docker.com/desktop/",
                )
                return False
            append_log(item, "[*] 通过 Homebrew 安装 Docker Desktop ...")
            code = _run_stream(item, docker_desktop_brew_command(brew), timeout=3600)
            if code != 0:
                append_log(item, "[!] brew install docker 失败")
                return False
            docker = which_enriched("docker")
            if not docker:
                append_log(
                    item,
                    "[!] Docker 已安装但当前会话找不到命令，请重启程序后再点一键部署",
                )
                return False
        else:
            # Linux：官方脚本安装（curl + 免密 sudo），失败给手动指引
            append_log(item, "[*] 通过官方脚本安装 Docker（需要 sudo 免密授权）...")
            code = _run_stream(item, docker_linux_install_command(), timeout=3600)
            if code != 0:
                append_log(item, "[!] Docker 自动安装失败，请参考手动安装：")
                append_log(item, "    https://docs.docker.com/engine/install/")
                return False
            docker = which_enriched("docker")
            if not docker:
                append_log(
                    item, "[!] Docker 已安装但未找到命令，请重启程序后再点一键部署"
                )
                return False

    # 2) daemon 未运行 → 尝试启动并等待就绪
    if not check_docker_running(docker):
        append_log(item, "[*] Docker daemon 未运行，尝试启动（可能需要 1-2 分钟）...")
        _try_start_docker(item)
        if not _wait_docker(docker, 300):
            append_log(
                item,
                "[!] Docker daemon 等待超时；若是刚安装的 Docker Desktop，可能需要重启系统后再试",
            )
            return False
        append_log(item, "[+] Docker daemon 已就绪")

    # 3) 多源拉取沙盒镜像并打标签（自定义源 → ghcr.io → 公共代理，失败自动换源）
    if check_image_exists(docker, SANDBOX_IMAGE_TAG):
        append_log(item, f"[*] 镜像 {SANDBOX_IMAGE_TAG} 已存在，跳过拉取")
        return True
    ok = pull_sandbox_image(
        docker, log=lambda line: append_log(item, line), timeout=3600
    )
    if not ok:
        append_log(item, "[!] 所有镜像源均拉取失败")
        append_log(item, "    可在上方「镜像源」填写自定义源后重试")
        append_log(
            item,
            "    或手动拉取任一源后执行: docker tag <镜像> my_agent_env:latest",
        )
        return False
    if not check_image_exists(docker, SANDBOX_IMAGE_TAG):
        append_log(item, "[!] 镜像拉取流程完成但未检测到目标镜像")
        return False
    append_log(item, f"[+] 沙盒镜像已就绪: {SANDBOX_IMAGE_TAG}")
    return True


def install_embedding(item: str) -> bool:
    from src.utils.config import is_data_root_configured
    from src.utils.embedding_setup import (
        EMBEDDING_DIR,
        MODEL_NAME,
        _model_exists,
        download_model,
    )

    if not is_data_root_configured():
        append_log(item, "[!] 数据根目录尚未配置，请先在配置中心完成数据盘设置并重启")
        return False
    if _model_exists(EMBEDDING_DIR):
        append_log(item, "[*] 嵌入模型已存在，跳过下载")
        return True

    def log(m):
        append_log(item, m)

    try:
        append_log(
            item, f"[*] 下载嵌入模型 {MODEL_NAME}（int8 约 113MB，自动多源回退）..."
        )
        download_model(log=log)
        append_log(item, "[+] 嵌入模型下载完成")
    except Exception as e:
        append_log(item, f"[!] 嵌入模型下载失败: {e}")
        return False
    return _model_exists(EMBEDDING_DIR)


INSTALLERS = {
    "uv": install_uv,
    "node": install_node,
    "sandbox": install_sandbox,
    "embedding": install_embedding,
}

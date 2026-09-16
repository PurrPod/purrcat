"""
部署中心：运行环境依赖的状态检测与一键安装
配置中心「部署」标签页的后端支撑：
  - check_all()    各依赖项（uv / node / sandbox / embedding）当前就绪状态
  - start_deploy() 后台线程执行单项安装，日志收集在内存
  - get_overview() 就绪状态 + 任务进度合并视图（前端轮询）
安装完成后依赖注册表 PATH 变更（get_enriched_env 可立即感知），
但主程序完整生效仍建议重启（前端会提示）。
"""

import os
import shutil
import subprocess
import sys
import threading
import time

from src.utils.config import get_enriched_env

DEPLOY_ITEMS = ("uv", "node", "sandbox", "embedding")

# 每项日志滚动保留的最大行数
MAX_LOG_LINES = 200
# 状态检测缓存：前端轮询 2.5s 一次，避免每次都跑 docker info 等子进程
CHECK_CACHE_TTL = 5

_WIN = sys.platform.startswith("win")
_MAC = sys.platform == "darwin"
_SUBPROC_ENCODING = "gbk" if _WIN else "utf-8"

# 常见用户级安装目录：已运行进程的 PATH 通常不包含，但刚装完的命令就在这里
# （uv 官方脚本三平台统一装到 ~/.local/bin；Homebrew 在 /opt/homebrew/bin 或 /usr/local/bin）
_EXTRA_BIN_DIRS = [
    os.path.expanduser("~/.local/bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
]

# item -> {"state": idle|running|success|failed, "log": [str], "finished_at": float|None}
_tasks: dict = {
    item: {"state": "idle", "log": [], "finished_at": None} for item in DEPLOY_ITEMS
}
_lock = threading.Lock()
_check_cache: dict = {"at": 0.0, "data": None}


def _append_log(item: str, line: str) -> None:
    with _lock:
        task = _tasks[item]
        task["log"] = (task["log"] + [line])[-MAX_LOG_LINES:]


def _which_enriched(name: str) -> str | None:
    """用合并注册表后的 PATH 查找命令（用户刚装完、没重启程序时也能找到）；
    找不到时再查常见用户级安装目录（~/.local/bin、Homebrew bin 等），
    命中后并入当前进程 PATH，让后续 subprocess 也能直接用"""
    found = shutil.which(name, path=get_enriched_env().get("PATH"))
    if found:
        return found
    for d in _EXTRA_BIN_DIRS:
        if not os.path.isdir(d):
            continue
        found = shutil.which(name, path=d)
        if found:
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + d
            return found
    return None


def _run_stream(item: str, cmd: list, timeout: float | None = None) -> int:
    """执行命令，stdout/stderr 逐行流式写入 item 日志；返回退出码（异常/超时返回 -1）"""
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=_SUBPROC_ENCODING,
            errors="replace",
            bufsize=1,
            env=get_enriched_env(),
        )
    except Exception as e:
        _append_log(item, f"[!] 启动命令失败: {cmd[0]}: {e}")
        return -1

    def _pump():
        try:
            for line in proc.stdout:
                _append_log(item, line.rstrip())
        except Exception:
            pass

    reader = threading.Thread(target=_pump, daemon=True)
    reader.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        _append_log(item, f"[!] 超时（{int(timeout)}秒），已终止")
        return -1
    reader.join(timeout=5)
    return proc.returncode


def _quick_version(cmd: list) -> str:
    """拿命令首行版本信息（如 uv --version），失败返回空串"""
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            encoding=_SUBPROC_ENCODING,
            errors="replace",
            env=get_enriched_env(),
        )
        out = (r.stdout or r.stderr or "").strip()
        return out.splitlines()[0] if out else ""
    except Exception:
        return ""


# ══════════════ 状态检测 ══════════════


def _check_uv() -> dict:
    path = _which_enriched("uv")
    if not path:
        return {"ready": False, "detail": "未检测到 uv 命令"}
    version = _quick_version([path, "--version"])
    return {"ready": True, "detail": version or path}


def _check_node() -> dict:
    path = _which_enriched("node")
    if not path:
        return {"ready": False, "detail": "未检测到 node 命令"}
    version = _quick_version([path, "--version"])
    return {"ready": True, "detail": version or path}


def _check_sandbox() -> dict:
    from src.utils.sandbox_setup import (
        SANDBOX_IMAGE_TAG,
        check_docker_running,
        check_image_exists,
    )

    result = {
        "ready": False,
        "docker_installed": False,
        "docker_running": False,
        "image_ready": False,
        "detail": "未检测到 Docker",
    }
    docker = _which_enriched("docker")
    if not docker:
        return result
    result["docker_installed"] = True
    if not check_docker_running(docker):
        result["detail"] = "Docker 已安装，但 daemon 未运行"
        return result
    result["docker_running"] = True
    if not check_image_exists(docker, SANDBOX_IMAGE_TAG):
        result["detail"] = f"Docker 正常，镜像 {SANDBOX_IMAGE_TAG} 未拉取"
        return result
    result["image_ready"] = True
    result["ready"] = True
    result["detail"] = f"镜像 {SANDBOX_IMAGE_TAG} 已就绪"
    return result


def _check_embedding() -> dict:
    from src.utils.dependency_check import _check_embedding as _exists
    from src.utils.embedding_setup import EMBEDDING_DIR

    if _exists():
        return {"ready": True, "detail": f"模型已就绪: {EMBEDDING_DIR}"}
    from src.utils.config import is_data_root_configured

    if not is_data_root_configured():
        return {"ready": False, "detail": "数据根目录尚未配置，配置并重启后才能下载"}
    return {"ready": False, "detail": "嵌入模型未下载（约 120MB）"}


_CHECKERS = {
    "uv": _check_uv,
    "node": _check_node,
    "sandbox": _check_sandbox,
    "embedding": _check_embedding,
}


def check_all() -> dict:
    """所有依赖项就绪状态（带短缓存，供前端高频轮询）"""
    now = time.time()
    if _check_cache["data"] is not None and now - _check_cache["at"] < CHECK_CACHE_TTL:
        return _check_cache["data"]
    data = {item: checker() for item, checker in _CHECKERS.items()}
    _check_cache["at"] = now
    _check_cache["data"] = data
    return data


# ══════════════ 安装实现 ══════════════


def _install_uv(item: str) -> bool:
    _append_log(item, "[*] 通过官方安装脚本安装 uv ...")
    if _WIN:
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "irm https://astral.sh/uv/install.ps1 | iex",
        ]
    else:
        cmd = ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]
    code = _run_stream(item, cmd, timeout=600)
    if code != 0:
        _append_log(item, "[!] uv 安装脚本执行失败，请检查网络后重试")
        return False
    if not _which_enriched("uv"):
        _append_log(item, "[!] 脚本已执行但未找到 uv 命令，请重启程序后重试")
        return False
    _append_log(item, f"[+] uv 安装成功: {_which_enriched('uv')}")
    return True


def _install_node(item: str) -> bool:
    if _WIN:
        winget = _which_enriched("winget")
        if not winget:
            _append_log(
                item, "[!] 未检测到 winget，请手动安装 Node.js: https://nodejs.org/"
            )
            return False
        _append_log(
            item, "[*] 通过 winget 安装 Node.js LTS（安装包较大，请耐心等待）..."
        )
        code = _run_stream(
            item,
            [
                winget,
                "install",
                "--id",
                "OpenJS.NodeJS.LTS",
                "-e",
                "--accept-source-agreements",
                "--accept-package-agreements",
            ],
            timeout=1800,
        )
        if code != 0:
            _append_log(item, "[!] winget 安装失败，可手动安装: https://nodejs.org/")
            return False
    elif _MAC:
        brew = _which_enriched("brew")
        if not brew:
            _append_log(
                item, "[!] 未检测到 Homebrew，请手动安装 Node.js: https://nodejs.org/"
            )
            return False
        _append_log(item, "[*] 通过 Homebrew 安装 Node.js ...")
        code = _run_stream(item, [brew, "install", "node"], timeout=1800)
        if code != 0:
            _append_log(item, "[!] brew install node 失败")
            return False
    else:
        # Linux：逐个尝试发行版包管理器（sudo 免密场景可直接装，否则给出手动指引）
        pkg_mgrs = [
            ("apt-get", ["sudo", "-n", "apt-get", "install", "-y", "nodejs", "npm"]),
            ("dnf", ["sudo", "-n", "dnf", "install", "-y", "nodejs", "npm"]),
            ("yum", ["sudo", "-n", "yum", "install", "-y", "nodejs", "npm"]),
            ("pacman", ["sudo", "-n", "pacman", "-S", "--noconfirm", "nodejs", "npm"]),
        ]
        for mgr, cmd in pkg_mgrs:
            if not _which_enriched(mgr):
                continue
            _append_log(item, f"[*] 通过 {mgr} 安装 Node.js（需要 sudo 免密授权）...")
            if _run_stream(item, cmd, timeout=1800) == 0 and _which_enriched("node"):
                break
            _append_log(item, f"[!] {mgr} 安装失败，尝试下一种方式")
        else:
            _append_log(item, "[!] 自动安装失败。请手动安装 Node.js，例如：")
            _append_log(
                item, "    sudo apt-get install -y nodejs npm   # Debian/Ubuntu"
            )
            _append_log(item, "    或参考 https://nodejs.org/en/download")
            return False
    if not _which_enriched("node"):
        _append_log(item, "[!] 安装完成但未找到 node 命令，请重启程序后重试")
        return False
    _append_log(
        item,
        f"[+] Node.js 安装成功: {_quick_version([_which_enriched('node'), '--version'])}",
    )
    return True


def _try_start_docker(item: str) -> None:
    """尝试拉起 Docker Desktop / dockerd（拉不起就等超时由调用方兜底）"""
    if _WIN:
        candidates = [
            r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Docker\Docker Desktop.exe"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                try:
                    subprocess.Popen([p], close_fds=True)
                    _append_log(item, f"[*] 已启动 Docker Desktop: {p}")
                    return
                except Exception as e:
                    _append_log(item, f"[!] 启动 Docker Desktop 失败: {e}")
                    return
        _append_log(item, "[!] 未找到 Docker Desktop，请手动启动")
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


def _install_sandbox(item: str) -> bool:
    from src.utils.sandbox_setup import (
        SANDBOX_IMAGE_TAG,
        check_docker_running,
        check_image_exists,
        pull_sandbox_image,
    )

    docker = _which_enriched("docker")

    # 1) 无 Docker CLI → 安装 Docker Desktop
    if not docker:
        if _WIN:
            winget = _which_enriched("winget")
            if not winget:
                _append_log(
                    item,
                    "[!] 未检测到 winget，请手动安装 Docker Desktop: https://docs.docker.com/desktop/",
                )
                return False
            _append_log(
                item, "[*] 通过 winget 安装 Docker Desktop（体积大，耗时较长）..."
            )
            code = _run_stream(
                item,
                [
                    winget,
                    "install",
                    "--id",
                    "Docker.DockerDesktop",
                    "-e",
                    "--accept-source-agreements",
                    "--accept-package-agreements",
                ],
                timeout=3600,
            )
            if code != 0:
                _append_log(
                    item,
                    "[!] Docker Desktop 安装失败，可手动安装: https://docs.docker.com/desktop/",
                )
                return False
            docker = _which_enriched("docker")
            if not docker:
                _append_log(
                    item,
                    "[!] Docker 已安装但当前会话找不到命令，请重启程序后再点一键部署",
                )
                return False
        elif _MAC:
            brew = _which_enriched("brew")
            if not brew:
                _append_log(
                    item,
                    "[!] 未检测到 Homebrew，请手动安装 Docker Desktop: https://docs.docker.com/desktop/",
                )
                return False
            _append_log(item, "[*] 通过 Homebrew 安装 Docker Desktop ...")
            code = _run_stream(
                item, [brew, "install", "--cask", "docker"], timeout=3600
            )
            if code != 0:
                _append_log(item, "[!] brew install docker 失败")
                return False
            docker = _which_enriched("docker")
            if not docker:
                _append_log(
                    item,
                    "[!] Docker 已安装但当前会话找不到命令，请重启程序后再点一键部署",
                )
                return False
        else:
            # Linux：官方脚本安装（curl + 免密 sudo），失败给手动指引
            _append_log(item, "[*] 通过官方脚本安装 Docker（需要 sudo 免密授权）...")
            code = _run_stream(
                item,
                ["sh", "-c", "curl -fsSL https://get.docker.com | sudo -n sh"],
                timeout=3600,
            )
            if code != 0:
                _append_log(item, "[!] Docker 自动安装失败，请参考手动安装：")
                _append_log(item, "    https://docs.docker.com/engine/install/")
                return False
            docker = _which_enriched("docker")
            if not docker:
                _append_log(
                    item, "[!] Docker 已安装但未找到命令，请重启程序后再点一键部署"
                )
                return False

    # 2) daemon 未运行 → 尝试启动并等待就绪
    if not check_docker_running(docker):
        _append_log(item, "[*] Docker daemon 未运行，尝试启动（可能需要 1-2 分钟）...")
        _try_start_docker(item)
        if not _wait_docker(docker, 300):
            _append_log(
                item,
                "[!] Docker daemon 等待超时；若是刚安装的 Docker Desktop，可能需要重启系统后再试",
            )
            return False
        _append_log(item, "[+] Docker daemon 已就绪")

    # 3) 多源拉取沙盒镜像并打标签（自定义源 → ghcr.io → 公共代理，失败自动换源）
    if check_image_exists(docker, SANDBOX_IMAGE_TAG):
        _append_log(item, f"[*] 镜像 {SANDBOX_IMAGE_TAG} 已存在，跳过拉取")
        return True
    ok = pull_sandbox_image(
        docker, log=lambda line: _append_log(item, line), timeout=3600
    )
    if not ok:
        _append_log(item, "[!] 所有镜像源均拉取失败")
        _append_log(item, "    可在上方「镜像源」填写自定义源后重试")
        _append_log(
            item,
            "    或手动拉取任一源后执行: docker tag <镜像> my_agent_env:latest",
        )
        return False
    if not check_image_exists(docker, SANDBOX_IMAGE_TAG):
        _append_log(item, "[!] 镜像拉取流程完成但未检测到目标镜像")
        return False
    _append_log(item, f"[+] 沙盒镜像已就绪: {SANDBOX_IMAGE_TAG}")
    return True


def _install_embedding(item: str) -> bool:
    from src.utils.config import is_data_root_configured
    from src.utils.embedding_setup import (
        EMBEDDING_DIR,
        MODEL_NAME,
        _model_exists,
        download_model,
    )

    if not is_data_root_configured():
        _append_log(item, "[!] 数据根目录尚未配置，请先在配置中心完成数据盘设置并重启")
        return False
    if _model_exists(EMBEDDING_DIR):
        _append_log(item, "[*] 嵌入模型已存在，跳过下载")
        return True

    def log(m):
        _append_log(item, m)

    try:
        _append_log(item, f"[*] 下载嵌入模型 {MODEL_NAME}（~500MB，请保持网络稳定）...")
        download_model(log=log)
        _append_log(item, "[+] 嵌入模型下载完成")
    except Exception as e:
        _append_log(item, f"[!] 直连 huggingface.co 失败: {e}")
        _append_log(item, "[*] 切换 hf-mirror.com 镜像重试...")
        try:
            download_model("https://hf-mirror.com", log=log)
            _append_log(item, "[+] 嵌入模型（镜像）下载完成")
        except Exception as e2:
            _append_log(item, f"[!] 嵌入模型下载失败: {e2}")
            return False
    return _model_exists(EMBEDDING_DIR)


_INSTALLERS = {
    "uv": _install_uv,
    "node": _install_node,
    "sandbox": _install_sandbox,
    "embedding": _install_embedding,
}


# ══════════════ 任务管理 ══════════════


def start_deploy(item: str) -> tuple[bool, str]:
    """启动单项部署（后台线程）；已在运行中则拒绝。返回 (ok, message)"""
    if item not in DEPLOY_ITEMS:
        return False, f"未知部署项: {item}"
    with _lock:
        if _tasks[item]["state"] == "running":
            return False, "该依赖正在部署中，请在日志中查看进度"
        _tasks[item] = {
            "state": "running",
            "log": [f"[{time.strftime('%H:%M:%S')}] 开始部署 {item}"],
            "finished_at": None,
        }

    def _worker():
        try:
            ok = _INSTALLERS[item](item)
        except Exception as e:
            ok = False
            _append_log(item, f"[!] 部署异常: {e}")
        with _lock:
            _tasks[item]["state"] = "success" if ok else "failed"
            _tasks[item]["finished_at"] = time.time()
        _append_log(
            item,
            "[+] 部署成功，重启程序后生效"
            if ok
            else "[!] 部署失败，可根据日志排查后重试",
        )

    threading.Thread(target=_worker, daemon=True).start()
    return True, "部署已启动"


def get_overview() -> dict:
    """前端轮询视图：各依赖项就绪状态 + 部署任务进度与日志"""
    items = check_all()
    with _lock:
        tasks = {
            k: {
                "state": v["state"],
                "log": list(v["log"]),
                "finished_at": v["finished_at"],
            }
            for k, v in _tasks.items()
        }
    return {"items": items, "tasks": tasks}

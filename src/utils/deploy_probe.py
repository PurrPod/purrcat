"""部署中心的状态检测（带短缓存，供前端高频轮询）。"""

import os
import shutil
import time

from src.utils._proc import run_text
from src.utils.config import get_enriched_env

# 状态检测缓存：前端轮询 2.5s 一次，避免每次都跑 docker info 等子进程
CHECK_CACHE_TTL = 5

# 常见用户级安装目录：已运行进程的 PATH 通常不包含，但刚装完的命令就在这里
# （uv 官方脚本三平台统一装到 ~/.local/bin；Homebrew 在 /opt/homebrew/bin 或 /usr/local/bin）
_EXTRA_BIN_DIRS = [
    os.path.expanduser("~/.local/bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
]

_check_cache: dict = {"at": 0.0, "data": None}


def which_enriched(name: str) -> str | None:
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


def quick_version(cmd: list) -> str:
    """拿命令首行版本信息（如 uv --version），失败返回空串"""
    try:
        r = run_text(cmd, timeout=15, env=get_enriched_env())
        out = (r.stdout or r.stderr or "").strip()
        return out.splitlines()[0] if out else ""
    except Exception:
        return ""


def check_uv() -> dict:
    path = which_enriched("uv")
    if not path:
        return {"ready": False, "detail": "未检测到 uv 命令"}
    version = quick_version([path, "--version"])
    return {"ready": True, "detail": version or path}


def check_node() -> dict:
    path = which_enriched("node")
    if not path:
        return {"ready": False, "detail": "未检测到 node 命令"}
    version = quick_version([path, "--version"])
    return {"ready": True, "detail": version or path}


def check_sandbox() -> dict:
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
    docker = which_enriched("docker")
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


def check_embedding() -> dict:
    from src.utils.dependency_check import _check_embedding as _exists
    from src.utils.embedding_setup import EMBEDDING_DIR

    if _exists():
        return {"ready": True, "detail": f"模型已就绪: {EMBEDDING_DIR}"}
    from src.utils.config import is_data_root_configured

    if not is_data_root_configured():
        return {"ready": False, "detail": "数据根目录尚未配置，配置并重启后才能下载"}
    return {"ready": False, "detail": "嵌入模型未下载（约 120MB）"}


_CHECKERS = {
    "uv": check_uv,
    "node": check_node,
    "sandbox": check_sandbox,
    "embedding": check_embedding,
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

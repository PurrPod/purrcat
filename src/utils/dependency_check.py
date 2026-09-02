"""
启动时依赖就绪检查
每次启动时检查：git / 嵌入模型 / 沙盒容器 / uv / node
若任一缺失或未就绪，向 requests.json 写入一条 dependency_check 类型 pending 请求，
前端 ChatPage 的 pending 队列会自动渲染，用户可确认跳转部署指南、取消或静默忽略。
"""

import json
import os
import shutil
import time

from src.tool.request.request_operations import (
    REQUESTS_FILE,
    REQUEST_LOCK,
    _ensure_requests_file,
)
from src.utils.config import get_enriched_env

DEPLOYMENT_GUIDE_URL = "https://purrpod.github.io/guide/deployment.html"
# 固定 req_id：避免每次重启堆积重复请求；启动时整体替换为最新检查结果
DEP_REQ_ID = "req_dep_check_startup"

# 合并注册表最新 PATH 后再检测：用户装完依赖没重启电脑时，
# 进程自身 PATH 还是旧的，直接 which 会误报"依赖缺失"
_ENRICHED_PATH = get_enriched_env().get("PATH")


def _check_git() -> bool:
    return shutil.which("git", path=_ENRICHED_PATH) is not None


def _check_uv() -> bool:
    return shutil.which("uv", path=_ENRICHED_PATH) is not None


def _check_node() -> bool:
    return shutil.which("node", path=_ENRICHED_PATH) is not None


def _check_embedding() -> bool:
    """复用 embedding_setup 的私有 _model_exists 判定（不触发下载）"""
    from src.utils.config import get_embedding_model
    from src.utils.embedding_setup import EMBEDDING_DIR, _model_exists

    target = get_embedding_model()
    # 1) 配置的绝对路径已完整
    if os.path.isabs(target) and _model_exists(target):
        return True
    # 2) 配置就是 EMBEDDING_DIR 且已完整
    if os.path.abspath(target) == os.path.abspath(EMBEDDING_DIR) and _model_exists(
        EMBEDDING_DIR
    ):
        return True
    # 3) EMBEDDING_DIR 本身已完整（SentenceTransformer fallback 路径）
    if _model_exists(EMBEDDING_DIR):
        return True
    return False


def _check_sandbox():
    """返回 (is_ready: bool, reason: str)"""
    from src.utils.sandbox_setup import (
        SANDBOX_IMAGE_TAG,
        check_docker_running,
        check_image_exists,
        docker_cmd,
    )

    docker = docker_cmd()
    if not docker:
        return False, "未检测到 Docker，沙盒（Bash 执行）将不可用。"
    if not check_docker_running(docker):
        return False, "Docker daemon 未启动，请先启动 Docker Desktop。"
    if not check_image_exists(docker, SANDBOX_IMAGE_TAG):
        return False, f"沙盒镜像 {SANDBOX_IMAGE_TAG} 不存在（首次启动会后台拉取）。"
    return True, ""


def check_and_warn_dependencies() -> None:
    """
    启动时统一检查所有依赖；缺失则写入/覆盖一条 pending 请求到 requests.json。
    - 已存在旧的同 ID 请求会被覆盖（保证反映最新检查结果）
    - 全部就绪时移除旧请求，不写入新请求
    - 幂等、线程安全（持有 REQUEST_LOCK）
    """
    missing = []
    if not _check_git():
        missing.append(
            {
                "name": "git",
                "reason": "未检测到 git 命令，文件版本控制与分支功能将不可用。",
            }
        )
    if not _check_uv():
        missing.append(
            {"name": "uv", "reason": "未检测到 uv 命令，Python 依赖管理将不可用。"}
        )
    if not _check_node():
        missing.append(
            {
                "name": "node",
                "reason": "未检测到 node 命令，部分 MCP Server / 工具将不可用。",
            }
        )
    if not _check_embedding():
        from src.utils.config import is_data_root_configured

        if is_data_root_configured():
            reason = "嵌入模型未就绪（首次启动会后台下载，可能仍在进行中）。"
        else:
            reason = "嵌入模型未就绪（数据根目录尚未配置，配置好并重启后会自动下载）。"
        missing.append({"name": "embedding", "reason": reason})
    sandbox_ok, sandbox_reason = _check_sandbox()
    if not sandbox_ok:
        missing.append({"name": "sandbox", "reason": sandbox_reason})

    _ensure_requests_file()
    with REQUEST_LOCK:
        try:
            with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = {}

        # 移除旧的依赖检查请求（无论本次结果如何都先清掉，避免残留）
        data.pop(DEP_REQ_ID, None)

        # 全部就绪 → 不写入新请求
        if not missing:
            try:
                with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except OSError:
                pass
            return

        reason_lines = "\n".join(f"- {m['name']}: {m['reason']}" for m in missing)
        req_data = {
            "id": DEP_REQ_ID,
            "type": "dependency_check",
            "target": f"启动依赖检查（{len(missing)} 项缺失）",
            "reason": f"以下依赖缺失或未就绪：\n{reason_lines}",
            "missing": [m["name"] for m in missing],
            "guide_url": DEPLOYMENT_GUIDE_URL,
            "status": "pending",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        data[DEP_REQ_ID] = req_data
        try:
            with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

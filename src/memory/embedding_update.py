"""嵌入模型更新任务：换模型 + 重建向量库。

前端通过两个接口驱动：
- ``GET /api/config/memory/embedding`` 读取模型状态与任务状态
- ``POST /api/config/memory/embedding/update`` 启动更新（运行中返回 409）

任务在后台线程执行，阶段写入 ``DATA_ROOT/embedding_update.json``；
进程中途退出后重启，标记仍为 running，接口返回 ``interrupted=true``。
"""

from __future__ import annotations

import json
import os
import threading
import time

from src.memory.reindex import rebuild_vector_index
from src.utils.config import DATA_ROOT
from src.utils.embedding_manifest import MODEL_NAME, MODEL_TAG, model_dir_state
from src.utils.embedding_setup import (
    EMBEDDING_DIR,
    cleanup_install_artifacts,
    install_embedding_model,
)

MARKER_PATH = os.path.join(DATA_ROOT, "embedding_update.json")

_lock = threading.Lock()
_running = threading.Event()
_state = {
    "state": "idle",
    "phase": "",
    "message": "",
    "error": "",
    "report": None,
    "started_at": None,
    "finished_at": None,
}

_PHASE_TEXT = {
    "checking": "检查模型",
    "downloading": "下载嵌入模型",
    "rebuilding": "重建向量库",
    "done": "已完成",
}


def embedding_model_state() -> dict:
    """当前模型目录相对期望模型的状态。"""
    state = model_dir_state(EMBEDDING_DIR)
    return {
        "status": state,
        "dir": EMBEDDING_DIR,
        "model": MODEL_NAME,
        "tag": MODEL_TAG,
    }


def update_status() -> dict:
    """任务状态 + 上次中断检测。"""
    with _lock:
        snapshot = dict(_state)
    marker = _read_marker()
    snapshot["interrupted"] = bool(
        marker
        and marker.get("state") == "running"
        and not _running.is_set()
        and snapshot["state"] != "running"
    )
    snapshot["marker"] = marker or {}
    return snapshot


def start_update() -> dict:
    """启动更新任务；已有任务运行时返回 started=False。"""
    with _lock:
        if _running.is_set():
            return {"started": False, "status": dict(_state)}
        _running.set()
        _state.update(
            state="running",
            phase="checking",
            message=_PHASE_TEXT["checking"],
            error="",
            report=None,
            started_at=_now(),
            finished_at=None,
        )
        snapshot = dict(_state)
    _write_marker()

    thread = threading.Thread(target=run_update, daemon=True, name="embedding-update")
    thread.start()
    return {"started": True, "status": snapshot}


def run_update(log=print) -> dict:
    """同步执行更新（测试直接调用；生产由后台线程触发）。"""
    try:
        if model_dir_state(EMBEDDING_DIR) != "current":
            _release_runtime_embedder(log)
            _set_phase("downloading", log)
            install_embedding_model(log=log)
            # 替换后再次清理，确保重建使用新权重编码
            _release_runtime_embedder(log)
        else:
            log("[*] 嵌入模型已是当前版本，跳过下载")

        _set_phase("rebuilding", log)
        report = rebuild_vector_index(log=log)
        with _lock:
            _state.update(
                state="done",
                phase="done",
                message=_PHASE_TEXT["done"],
                report=report,
                error="",
                finished_at=_now(),
            )
        _write_marker()
        return update_status()
    except Exception as e:
        with _lock:
            _state.update(state="error", error=str(e), finished_at=_now())
            _state["message"] = f"更新失败：{e}"
        _write_marker()
        log(f"[!] 嵌入模型更新失败：{e}")
        return update_status()
    finally:
        _running.clear()


def _set_phase(phase: str, log=print) -> None:
    with _lock:
        _state.update(phase=phase, message=_PHASE_TEXT.get(phase, phase))
    _write_marker()
    log(f"[*] 嵌入模型更新：{_PHASE_TEXT.get(phase, phase)}")


def _release_runtime_embedder(log=print) -> None:
    """清空编码器缓存与常驻检索实例，避免继续使用旧权重。"""
    from src.utils.local_embedding import reset_embedder_cache

    reset_embedder_cache()
    try:
        from src.memory.purrmemo.client import get_memory_client

        vector_engine = getattr(get_memory_client().search_tool, "vector_engine", None)
        if vector_engine is not None:
            vector_engine.reset_embedding_model()
    except Exception as e:
        log(f"    ! 释放常驻编码器失败（将按需重新加载）: {e}")


def _now() -> float:
    return round(time.time(), 3)


def _write_marker() -> None:
    with _lock:
        payload = {
            "state": _state["state"],
            "phase": _state["phase"],
            "message": _state["message"],
            "error": _state["error"],
            "started_at": _state["started_at"],
            "finished_at": _state["finished_at"],
        }
    try:
        os.makedirs(os.path.dirname(MARKER_PATH), exist_ok=True)
        tmp = MARKER_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, MARKER_PATH)
    except OSError:
        pass


def _read_marker() -> dict | None:
    try:
        with open(MARKER_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def cleanup_stale_install() -> None:
    """启动时清理中断残留的暂存/备份目录。"""
    cleanup_install_artifacts()

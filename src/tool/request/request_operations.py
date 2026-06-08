"""Request 工具单文件操作核心 - 直接写入 requests.json"""

import json
import os
import uuid
import time
import threading

from src.utils.config import DATA_DIR

# 统一存储在单文件 requests.json 中
REQUESTS_FILE = os.path.join(DATA_DIR, "checkpoints", "agent", "requests.json")
REQUEST_LOCK = threading.Lock()


def _ensure_requests_file():
    """确保 requests.json 文件存在"""
    os.makedirs(os.path.dirname(REQUESTS_FILE), exist_ok=True)
    if not os.path.exists(REQUESTS_FILE):
        with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)


def submit_request(request_type: str, target: str, reason: str) -> dict:
    """
    提交一个人类审批请求到 requests.json

    Args:
        request_type: 请求类型 (mcp_install/skill_install/file_write/file_read/sensor_install/graph_install)
        target: 目标对象 (文件路径或插件名称)
        reason: 申请理由

    Returns:
        包含请求详情的字典，包含 id, type, target, reason, status, created_at
    """
    _ensure_requests_file()

    req_id = f"req_{uuid.uuid4().hex[:8]}"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    req_data = {
        "id": req_id,
        "type": request_type,
        "target": target,
        "reason": reason,
        "status": "pending",  # 固定初始状态，等待人类给出 yes/no
        "created_at": timestamp,
    }

    with REQUEST_LOCK:
        try:
            with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = {}

        data[req_id] = req_data

        with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return req_data
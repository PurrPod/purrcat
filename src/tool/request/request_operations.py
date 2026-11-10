"""Request 工具单文件操作核心 - 直接写入 requests.json"""

import json
import os
import uuid
import time
import threading

from src.tool.request._shared import build_request_record
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


def read_requests() -> dict:
    """读取 requests.json；调用方按场景决定是否捕获异常。"""
    with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def write_requests(data: dict) -> None:
    with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def submit_request(
    request_type: str, target: str, reason: str, extra: dict = None
) -> dict:
    """
    提交一个人类审批请求到 requests.json

    Args:
        request_type: 请求类型（file_write/file_read 由 Request 工具发起；
              skill_test/sensor_test/*_merge 由 KernelUpgrade 工具代发）
        target: 目标对象 (文件路径或插件名称)
        reason: 申请理由
        extra: 附加字段（如 skill_test 的 trigger_started 标记）

    Returns:
        包含请求详情的字典，包含 id, type, target, reason, status, created_at
    """
    _ensure_requests_file()

    req_id = f"req_{uuid.uuid4().hex[:8]}"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    req_data = build_request_record(
        request_type, target, reason, req_id, timestamp, extra
    )

    with REQUEST_LOCK:
        try:
            data = read_requests()
        except json.JSONDecodeError:
            data = {}

        data[req_id] = req_data
        write_requests(data)

    return req_data

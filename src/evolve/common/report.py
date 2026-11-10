"""Evolve 报告与 JSON 文件读写（路径/编码约定集中于此）。"""

import json
import os
from datetime import datetime

REPORT_FILENAME = "report.html"


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: str):
    """读 JSON；文件缺失或损坏时返回 None（原有容错语义）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_json(path: str, data, newline=None) -> None:
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_text(path: str, text: str, newline=None) -> None:
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(text)


def write_report(iteration_dir: str, html: str) -> str:
    """把 HTML 报告写入迭代目录，返回完整路径。"""
    path = os.path.join(iteration_dir, REPORT_FILENAME)
    write_text(path, html)
    return path

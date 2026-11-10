"""PARADIGM 配置文件的加载与默认路径回退（纯函数）。"""

from __future__ import annotations

import os
from typing import Any

import yaml


def read_paradigm_config(path: str) -> dict[str, Any]:
    """读取 YAML 配置；解析异常抛给调用方决定是否保留旧配置。"""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def default_paradigm_path(
    user_path: str, paradigms_dir: str, fallback_path: str
) -> str:
    """优先用户配置；缺失时用内置模板就地生成，仍失败则回退系统模板。"""
    if os.path.exists(user_path):
        return user_path
    try:
        os.makedirs(paradigms_dir, exist_ok=True)
        # 默认模板定义在 src/utils/initial.py（懒加载，避免 import 环）
        from src.utils.initial import DEFAULT_PARADIGM_YAML

        with open(user_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_PARADIGM_YAML)
    except Exception:
        pass
    if os.path.exists(user_path):
        return user_path
    return fallback_path

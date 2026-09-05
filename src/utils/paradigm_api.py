"""PARADIGM（Agent Loop）配置文件的读写工具。

所有 Agent Loop 配置存放于 ~/.purrcat/paradigms/ 下，一个文件一个 loop：
  - PARADIGM.yaml 为默认 Agent Loop；
  - 其它文件为可切换编辑的备选 loop。
首次访问时若无 PARADIGM.yaml，用 src/utils/initial.py 里的默认模板就地生成一份再读取。
"""
import os
import re

import yaml

from src.utils.config import PARADIGMS_DIR

DEFAULT_FILE_NAME = "PARADIGM.yaml"
DEFAULT_FILE_BASE = "PARADIGM"  # 前端展示/路由用的 base 名

# 仅限制危险字符，允许中文等普通文件名
_INVALID_NAME = re.compile(r"[/\\:\x00-\x1f]")


def ensure_default_paradigm() -> str:
    """确保 paradigms 目录与默认 PARADIGM.yaml 存在（缺失时用 initial 里的模板生成），返回其路径。"""
    os.makedirs(PARADIGMS_DIR, exist_ok=True)
    target = os.path.join(PARADIGMS_DIR, DEFAULT_FILE_NAME)
    if not os.path.exists(target):
        # 模板定义在 initial.py（懒加载，避免 import 环）
        from src.utils.initial import DEFAULT_PARADIGM_YAML

        with open(target, "w", encoding="utf-8") as f:
            f.write(DEFAULT_PARADIGM_YAML)
    return target


def resolve_paradigm_path(name=None) -> str:
    """把范式名（不带 .yaml）解析为绝对路径；name 为空或缺文件时回落到默认 PARADIGM.yaml。"""
    if name:
        try:
            base = _safe_name(name)
        except ValueError:
            base = DEFAULT_FILE_BASE
        target = os.path.join(PARADIGMS_DIR, f"{base}.yaml")
        if os.path.exists(target):
            return target
    return ensure_default_paradigm()


def _safe_name(name: str) -> str:
    name = (name or "").strip().removesuffix(".yaml").removesuffix(".yml")
    if not name:
        raise ValueError("paradigm 名称不能为空")
    if name in {".", ".."} or name.startswith("."):
        raise ValueError("paradigm 名称不合法")
    if _INVALID_NAME.search(name) or len(name) > 60:
        raise ValueError("paradigm 名称包含不支持的字符")
    return name


safe_name = _safe_name  # 对外公开的别名，避免 API 层触碰私有函数


def _path_of(name: str) -> str:
    return os.path.join(PARADIGMS_DIR, f"{_safe_name(name)}.yaml")


def list_paradigms() -> list:
    """返回 {name, is_default} 列表，默认文件排在首位。"""
    ensure_default_paradigm()
    files = []
    for f in sorted(os.listdir(PARADIGMS_DIR)):
        if not f.endswith(".yaml"):
            continue
        base = f[: -len(".yaml")]
        if base == DEFAULT_FILE_BASE:
            files.insert(0, {"name": base, "is_default": True})
        else:
            files.append({"name": base, "is_default": False})
    if not files:
        ensure_default_paradigm()
        files = [{"name": DEFAULT_FILE_BASE, "is_default": True}]
    return files


def load_paradigm(name: str) -> dict:
    """读取并解析指定 paradigm，返回完整 dict（含顶层元信息与 hooks）。"""
    path = _path_of(name)
    if not os.path.exists(path):
        raise FileNotFoundError(name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"YAML 解析失败: {e}") from e
    return data if isinstance(data, dict) else {}


def save_paradigm(name: str, data: dict) -> str:
    """整体写回 paradigm 文件（保留键顺序）。返回写回后的路径。"""
    path = _path_of(name)
    os.makedirs(PARADIGMS_DIR, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                data if isinstance(data, dict) else {},
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
    except yaml.YAMLError as e:
        raise ValueError(f"YAML 序列化失败: {e}") from e
    return path


def delete_paradigm(name: str) -> None:
    base = _safe_name(name)
    if base == DEFAULT_FILE_BASE:
        raise ValueError("默认 PARADIGM.yaml 不允许删除")
    path = _path_of(base)
    if os.path.exists(path):
        os.remove(path)

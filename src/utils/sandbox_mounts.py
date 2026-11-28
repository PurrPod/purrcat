"""沙盒挂载配置（SPEC-045）。

用户在文件设置页把宿主文件夹映射到容器 ``/mount/<别名>``：
- 配置持久化在 ``~/.purrcat/mounts.json``，与文件权限配置分离；
- 容器创建/重建时按配置生成 bind mount；
- FileSystem 的 ``/mount/<别名>/...`` 走同一张表映射回宿主路径。

本模块只处理配置、校验与路径换算，不依赖 docker。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable

from src.utils.config import AGENT_VM_DIR, PURRCAT_DIR

MOUNTS_CONFIG_PATH = os.path.join(PURRCAT_DIR, "mounts.json")
CONTAINER_MOUNT_ROOT = "/mount"
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class MountError(ValueError):
    """挂载配置不合法。"""


def _norm(path: Any) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _within(child: str, parent: str) -> bool:
    try:
        return os.path.commonpath([_norm(child), _norm(parent)]) == _norm(parent)
    except ValueError:  # Windows 跨盘符
        return False


def normalize_source(value: Any) -> str:
    text = str(value or "").strip().strip('"')
    if not text:
        raise MountError("目录路径不能为空")
    if not os.path.isabs(text):
        raise MountError("请选择绝对路径")
    return os.path.normpath(text)


def sanitize_name(value: Any) -> str:
    text = re.sub(r"[^0-9A-Za-z_-]+", "-", str(value or "").strip()).strip("-_")
    return text[:64] or "mount"


def unique_name(base: str, existing: Iterable[str], skip: str | None = None) -> str:
    """生成大小写不敏感的唯一别名：冲突时追加 -2、-3。"""
    taken = {str(name).lower() for name in existing}
    if skip:
        taken.discard(str(skip).lower())
    candidate = sanitize_name(base)
    if candidate.lower() not in taken:
        return candidate
    index = 2
    while f"{candidate}-{index}".lower() in taken:
        index += 1
    return f"{candidate}-{index}"


def suggest_name(source: str, existing: Iterable[str]) -> str:
    base = os.path.basename(os.path.normpath(str(source))) or "mount"
    return unique_name(base, existing)


def _normalize_entries(entries: Any) -> list[dict]:
    if not isinstance(entries, list):
        return []
    mounts: list[dict] = []
    names: list[str] = []
    sources: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        try:
            source = normalize_source(item.get("source"))
        except MountError:
            continue
        key = _norm(source)
        if key in sources:
            continue
        raw_name = str(item.get("name") or "").strip()
        name = (
            raw_name
            if _NAME_RE.match(raw_name)
            else sanitize_name(os.path.basename(source))
        )
        name = unique_name(name, names)
        names.append(name)
        sources.add(key)
        mounts.append({"name": name, "source": source})
    return mounts


def load_mounts() -> list[dict]:
    """读取挂载配置；缺失、损坏或条目非法时忽略对应内容。"""
    try:
        with open(MOUNTS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    entries = data.get("mounts") if isinstance(data, dict) else data
    return _normalize_entries(entries)


def save_mounts(mounts: Iterable[dict]) -> bool:
    normalized = _normalize_entries(list(mounts))
    try:
        os.makedirs(os.path.dirname(MOUNTS_CONFIG_PATH), exist_ok=True)
        with open(MOUNTS_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"mounts": normalized}, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Mounts] 保存挂载配置失败: {e}")
        return False


def _ensure_writable_dir(source: str) -> None:
    if not os.path.isdir(source):
        raise MountError("目录不存在或不是文件夹")
    if not os.access(source, os.W_OK):
        raise MountError("目录没有写入权限")
    probe = os.path.join(source, f".purrcat-mount-check-{os.getpid()}")
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
    except OSError:
        raise MountError("目录不可写（只读磁盘或权限不足）") from None
    finally:
        try:
            os.remove(probe)
        except OSError:
            pass


def validate_new_mount(
    source: Any, name: str | None = None, mounts: list[dict] | None = None
) -> dict:
    """校验并返回待新增的挂载项；不写盘。"""
    current = load_mounts() if mounts is None else list(mounts)
    normalized = normalize_source(source)

    if _within(normalized, AGENT_VM_DIR) or _within(AGENT_VM_DIR, normalized):
        raise MountError("该目录与沙盒工作目录重叠，无需重复挂载")
    for item in current:
        if _norm(item["source"]) == _norm(normalized):
            raise MountError("该目录已经挂载")
        if _within(normalized, item["source"]) or _within(item["source"], normalized):
            raise MountError("该目录与已有挂载存在父子重叠")

    _ensure_writable_dir(normalized)

    existing_names = [str(item["name"]) for item in current]
    if name:
        candidate = str(name).strip()
        if not _NAME_RE.match(candidate):
            raise MountError(
                "名称只能包含字母、数字、下划线和短横线，且不超过 64 个字符"
            )
        if candidate.lower() in {n.lower() for n in existing_names}:
            raise MountError(f"名称 {candidate} 已被占用")
        final_name = candidate
    else:
        final_name = suggest_name(normalized, existing_names)
    return {"name": final_name, "source": normalized}


def add_mount(source: Any, name: str | None = None) -> dict:
    mounts = load_mounts()
    item = validate_new_mount(source, name, mounts)
    if not save_mounts(mounts + [item]):
        raise MountError("保存挂载配置失败")
    return item


def rename_mount(name: str, new_name: str) -> dict:
    mounts = load_mounts()
    target = next((m for m in mounts if m["name"].lower() == str(name).lower()), None)
    if target is None:
        raise MountError("挂载不存在")
    candidate = str(new_name or "").strip()
    if not _NAME_RE.match(candidate):
        raise MountError("名称只能包含字母、数字、下划线和短横线，且不超过 64 个字符")
    if any(m["name"].lower() == candidate.lower() and m is not target for m in mounts):
        raise MountError(f"名称 {candidate} 已被占用")
    target["name"] = candidate
    if not save_mounts(mounts):
        raise MountError("保存挂载配置失败")
    return dict(target)


def remove_mount(name: str) -> bool:
    mounts = load_mounts()
    kept = [m for m in mounts if m["name"].lower() != str(name).lower()]
    if len(kept) == len(mounts):
        raise MountError("挂载不存在")
    if not save_mounts(kept):
        raise MountError("保存挂载配置失败")
    return True


def container_mounts(mounts: list[dict] | None = None) -> list[dict]:
    """容器可用的挂载项（跳过源目录缺失的条目）。"""
    result = []
    for item in load_mounts() if mounts is None else mounts:
        if not os.path.isdir(item["source"]):
            continue
        result.append(
            {
                "name": item["name"],
                "source": item["source"],
                "destination": f"{CONTAINER_MOUNT_ROOT}/{item['name']}",
            }
        )
    return result


def resolve_mount_path(path: str, mounts: list[dict] | None = None) -> str | None:
    """把 /mount/<别名>/... 映射为宿主路径；未知别名或越界返回 None。"""
    text = str(path or "").strip().replace("\\", "/")
    if text.startswith("//mount/"):
        text = text[1:]
    if not text.startswith(CONTAINER_MOUNT_ROOT + "/"):
        return None
    rest = text[len(CONTAINER_MOUNT_ROOT) + 1 :]
    name, _, tail = rest.partition("/")
    entries = load_mounts() if mounts is None else mounts
    entry = next((m for m in entries if m["name"].lower() == name.lower()), None)
    if entry is None:
        return None
    root = os.path.abspath(entry["source"])
    parts = [part for part in tail.split("/") if part]
    target = os.path.abspath(os.path.join(root, *parts))
    if not _within(target, root):
        return None
    return target


def is_in_mount_source(path: str, mounts: list[dict] | None = None) -> bool:
    entries = load_mounts() if mounts is None else mounts
    return any(_within(path, item["source"]) for item in entries)


def mounts_prompt_lines(mounts: list[dict] | None = None) -> list[str]:
    """@SYS 展示用的「容器路径 -> 宿主路径」文本行。"""
    return [
        f"{item['destination']} -> {item['source']}"
        for item in container_mounts(mounts)
    ]

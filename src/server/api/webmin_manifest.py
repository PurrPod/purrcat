"""web-minimal 插件清单的纯归一化逻辑（无文件 IO）。

路由层负责扫描目录、探测后端与读取共享清单；本模块只做数据结构变换，
便于直接单测。
"""

from __future__ import annotations

import os

from src.server.api.common import (
    is_within_root,
    normalize_dependency_list as _normalize_dependency_list,
)

AREA_PANEL = "panel"
AREA_PET = "pet"  # 自由浮窗：可任意摆放/拖拽缩放，不干扰其它插件
AREA_POPUP = "popup"  # 模态弹窗：与设置中心同级，遮罩铺满主区

# 插件在宿主内的默认排列顺序
SLOT_ORDER = ("sidebar", "session", "background", "panel", "pet", "popup")


def plugin_area(p: dict) -> str:
    """插件声明所在区域（area 是唯一维度；字符串 slot 直接视作区域）。"""
    pid = str(p.get("id") or "")
    slot = p.get("slot")
    if isinstance(slot, dict):
        return str(slot.get("area") or pid)
    return str(slot or pid)


def area_behavior(area: str) -> str:
    """区域 → 宿主行为类别（panel=抽屉，pet=浮窗，popup=模态，其余=锚定）。"""
    if area == AREA_PANEL:
        return "panel"
    if area == AREA_PET:
        return "float"
    if area == AREA_POPUP:
        return "modal"
    return "fixed"


def slot_id(p: dict) -> str:
    """插件的 slot 分组键（panel 共享 panel；pet/popup 每插件独立键）。"""
    area = plugin_area(p)
    if area == AREA_PANEL:
        return "panel"
    if area == AREA_PET:
        return "float:" + str(p.get("id") or "")
    if area == AREA_POPUP:
        return "modal:" + str(p.get("id") or "")
    return area


def slot_def(p: dict) -> dict:
    """归一化 slot 声明：area 为唯一维度，行为类别按区域推导。"""
    area = plugin_area(p)
    out = {"type": area_behavior(area), "area": area}
    slot = p.get("slot")
    if isinstance(slot, dict):
        # float/modal 可选声明默认尺寸；center 仅对 float 有意义
        if isinstance(slot.get("size"), dict):
            out["size"] = slot["size"]
        if slot.get("center"):
            out["center"] = True
    return out


def normalize_dependency(raw, dep_types: tuple) -> list:
    """归一化 dependency：只保留白名单类型，统一为 {"type", "id"}。"""
    return _normalize_dependency_list(raw, dep_types)


def normalize_shared_catalog(raw) -> dict:
    """解析共享运行时清单，返回 {name: {version, base}}。"""
    data = {}
    if isinstance(raw, dict):
        for name, item in raw.items():
            if not isinstance(item, dict):
                continue
            version = str(item.get("version") or "").strip()
            base = str(item.get("base") or "").strip()
            if name and version and base:
                data[str(name)] = {"version": version, "base": base}
    return data


def normalize_requires(raw, catalog: dict) -> list:
    """归一化 requires：附带共享运行时的实际版本、base 与可用标记。"""
    out = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            name, rng = item.strip(), ""
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            rng = str(item.get("range") or "").strip()
        else:
            continue
        if not name:
            continue
        entry = catalog.get(name)
        out.append(
            {
                "name": name,
                "range": rng,
                "version": entry["version"] if entry else "",
                "base": entry["base"] if entry else "",
                "ok": bool(entry),
            }
        )
    return out


def is_builtin(plugin_dir: str, builtin_root: str) -> bool:
    """插件路径是否位于内置根目录。"""
    return is_within_root(builtin_root, plugin_dir)


def plugin_origin(plugin_dir: str, root_to_dir: dict) -> str:
    """插件实际所在的根（user / sandbox / builtin）；不在已知根内返回空串。"""
    abs_dir = os.path.abspath(plugin_dir)
    for name, root in root_to_dir.items():
        if is_within_root(root, abs_dir):
            return name
    return ""


def sort_plugins(plugins, ordered: tuple = SLOT_ORDER) -> list:
    """按 slot 顺序与名称排序（未知 slot 排最后）。"""
    return sorted(
        plugins,
        key=lambda p: (
            ordered.index(slot_id(p)) if slot_id(p) in ordered else 999,
            p.get("name", ""),
        ),
    )


def sanitize_rail(raw: dict) -> dict:
    """归一化图标栏状态：stage 只接受 0/1，opacity 夹紧到 [0,1]。"""
    try:
        stage = int(raw.get("stage"))
    except (TypeError, ValueError):
        stage = 0
    try:
        opacity = float(raw.get("opacity"))
    except (TypeError, ValueError):
        opacity = 1
    return {
        "stage": stage if 0 <= stage <= 1 else 0,
        "opacity": max(0.0, min(1.0, opacity)),
        "hidden": raw.get("hidden") if isinstance(raw.get("hidden"), dict) else {},
    }


def normalize_active(raw: dict) -> dict:
    """归一化单例槽选中项：只保留非空字符串/整数。"""
    return {
        str(k): str(v) for k, v in raw.items() if isinstance(v, (str, int)) and str(v)
    }


def build_manifest_entry(
    p: dict,
    stored_config,
    *,
    catalog: dict,
    dep_types: tuple,
    builtin: bool,
    backend,
    origin: str,
    root_to_dir: dict,
) -> dict:
    """在描述符上补齐 manifest 字段（config / root / slot / requires 等）。"""
    p = dict(p)
    p["configSchema"] = p.get("configSchema") or []
    p["config"] = dict(stored_config or {})
    p["builtin"] = builtin
    p["backend"] = backend
    declared_root = str(p.get("root") or "").strip()
    p["root"] = declared_root if declared_root in root_to_dir else ""
    p["origin"] = origin
    p["rootOk"] = (not p["root"]) or (p["root"] == origin)
    p["dependency"] = normalize_dependency(p.get("dependency"), dep_types)
    # 注意：必须基于原始 slot（仍为 dict）计算 slotDef，再把 slot 字符串化
    p["requires"] = normalize_requires(p.get("requires"), catalog)
    p["slotDef"] = slot_def(p)
    p["slot"] = slot_id(p)
    return p

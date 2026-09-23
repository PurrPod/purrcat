"""极简模式（web-minimal）插件 API。

与现有 React UI 完全独立：宿主为纯静态页面（ui/web-minimal），它通过本路由
获取插件清单、按需读取插件静态文件（热插拔），以及执行约定的后端动作协议
（callAction）。

插件来源：
  - 内置四件套：{BASE_DIR}/ui/web-minimal/plugins/builtin/*（随 App 分发，只读）
  - 用户插件：  {PURRCAT_DIR}/webmin-plugins/*（热插拔，同名 id 覆盖内置）

互不干扰原则：本文件只新增路由，不修改任何现有 /api/* 路由行为。
"""

import json
import os
import shutil
import hashlib

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.server.api import plugin_runtime
from src.utils.config import (
    BASE_DIR,
    PURRCAT_DIR,
    GRAPHS_DIR,
    get_global_settings,
    save_global_setting,
)

router = APIRouter(prefix="/api/webmin", tags=["WebMinimal"])

# 内置插件根目录（随 App 分发，只读）；用户插件根目录（热插拔）
BUILTIN_PLUGIN_ROOT = os.path.join(BASE_DIR, "ui", "web-minimal", "plugins", "builtin")
USER_PLUGIN_ROOT = os.path.join(PURRCAT_DIR, "webmin-plugins")
# 后台壁纸托管目录（用户选择的本地壁纸复制进来后自此统一静态托管）
WALLPAPER_DIR = os.path.join(PURRCAT_DIR, "webmin-wallpapers")
# 允许托管的壁纸扩展名
_WALLPAPER_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".mp4",
    ".webm",
    ".mov",
}


# ---- 插件配置持久化（复用 ~/.purrcat/settings.json）----
def _load_webmin_config() -> dict:
    """读 webminConfig：{ "plugins": { plugin_id: config } }。"""
    cfg = get_global_settings().get("webminConfig")
    return cfg if isinstance(cfg, dict) else {"plugins": {}}


def _save_webmin_config(cfg: dict) -> bool:
    return save_global_setting("webminConfig", cfg)


def _is_builtin(plugin_dir: str) -> bool:
    """某个插件路径是否位于内置根目录（决定能否被删除管理）。"""
    try:
        builtin_root = os.path.abspath(BUILTIN_PLUGIN_ROOT)
        return (
            os.path.commonpath([builtin_root, os.path.abspath(plugin_dir)])
            == builtin_root
        )
    except Exception:
        return False


# 可承载到后端的动作 id → 处理器
_ACTION_HANDLERS = {
    "switch_to_normal": lambda payload: save_global_setting("ui_mode", "normal"),
}


def _read_plugin_descriptor(plugin_dir: str) -> dict:
    """读取某插件文件夹的 plugin.json；不存在或非法则返回 None。"""
    desc_path = os.path.join(plugin_dir, "plugin.json")
    try:
        with open(desc_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("id"):
            data["dir"] = plugin_dir
            return data
    except Exception:
        pass
    return None


def _scan_plugins(root: str) -> dict:
    """扫描某个根目录下所有插件，返回 { plugin_id: descriptor }。"""
    result = {}
    if not os.path.isdir(root):
        return result
    for name in os.listdir(root):
        plugin_dir = os.path.join(root, name)
        if not os.path.isdir(plugin_dir):
            continue
        desc = _read_plugin_descriptor(plugin_dir)
        if desc:
            result[desc["id"]] = desc
    return result


def _slot_id(p: dict) -> str:
    """插件的 slot id（宿主分组键 / rail / 设置面板展示用）。

    仅声明窗口类型：fixed 取 area；panel 内容插件共享宿主单例容器固定键
    ``panel``；float 每插件独立键 ``float:{plugin_id}``。
    旧字符串声明按 pet→float、其余→fixed 归一。
    """
    pid = str(p.get("id") or "")
    slot = p.get("slot")
    if isinstance(slot, dict):
        typ = str(slot.get("type") or "fixed")
        if typ == "panel":
            # 所有 panel 内容插件共享宿主系统级单例容器 panel-container，分组键固定为 "panel"
            return "panel"
        if typ == "float":
            return "float:" + pid
        # fixed / 未知：以 area（回退 id）作为分组键
        return str(slot.get("area") or slot.get("id") or pid)
    lid = str(slot or "")
    if lid == "pet":
        return "float:" + pid
    return lid or pid


def _slot_def(p: dict) -> dict:
    """归一化插件的 slot 声明为简化的「窗口类型」语义。

    新模型：fixed（锚定单例，同 area 只取第一个生效）、panel（内容插件，入驻
    宿主系统级单例容器 panel-container，经容器右上角抽屉切换显示）与 float
    （弹窗，多插件各自独立、可拖拽可缩放）。缺省值用于兼容旧字符串声明。
    """
    pid = str(p.get("id") or "")
    slot = p.get("slot")
    if isinstance(slot, dict):
        typ = str(slot.get("type") or "fixed")
        if typ == "panel":
            # panel 内容插件：入驻宿主 panel-container 中栏，经容器右上角抽屉切换
            return {"type": "panel"}
        if typ == "float":
            return {"type": "float"}
        return {
            "type": "fixed",
            "area": str(slot.get("area") or slot.get("id") or pid),
        }
    # 旧字符串声明：pet 槽默认浮层（可拖拽可缩放），其余锚定单例
    lid = str(slot or "")
    if lid == "pet":
        return {"type": "float"}
    return {"type": "fixed", "area": lid or pid}


def _merge_plugins():
    """内置插件为底，用户同名插件覆盖（下重上）。返回按 slot 分组的列表。"""
    merged = _scan_plugins(BUILTIN_PLUGIN_ROOT)
    merged.update(_scan_plugins(USER_PLUGIN_ROOT))  # 用户覆盖内置
    plugins = list(merged.values())
    ordered = ["sidebar", "history", "input", "background", "conversation"]
    plugins.sort(
        key=lambda p: (
            ordered.index(_slot_id(p)) if _slot_id(p) in ordered else 999,
            p.get("name", ""),
        )
    )
    return plugins


def _resolve_plugin_file(plugin_id: str, rel_path: str) -> str | None:
    """在用户/内置插件根目录中定位插件文件，沙箱到插件目录内防路径穿越。"""
    rel_path = rel_path.replace("\\", "/").lstrip("/")
    for root in (USER_PLUGIN_ROOT, BUILTIN_PLUGIN_ROOT):
        if not os.path.isdir(root):
            continue
        plugin_dir = os.path.join(root, plugin_id)
        if not os.path.isdir(plugin_dir):
            continue
        abs_root = os.path.abspath(plugin_dir)
        abs_target = os.path.abspath(os.path.join(abs_root, rel_path))
        # 沙箱校验：目标必须在插件根目录内
        if os.path.commonpath([abs_root, abs_target]) != abs_root:
            return None
        if os.path.isfile(abs_target):
            return abs_target
    return None


@router.get("/manifest")
def api_webmin_manifest():
    """返回全局 ui_mode + 当前已扫描到的全部插件列表（未新增插件即热插拔可感知）。

    每条插件附 configSchema（插件自声明）与 config（webminConfig 中的已存值），
    有效配置 = configSchema 默认值 ∪ config 覆盖；backend 表明该插件是否自带后端。
    """
    stored_cfg = _load_webmin_config()
    stored = stored_cfg.get("plugins") or {}
    plugins = []
    for p in _merge_plugins():
        p = dict(p)
        p["configSchema"] = p.get("configSchema") or []
        p["config"] = dict(stored.get(p["id"]) or {})
        p["builtin"] = _is_builtin(p.get("dir") or "")
        p["backend"] = _plugin_backend_info(p.get("dir") or "")
        # slot 归一化：p["slot"] 始终为字符串(id)；完整语义放 p["slotDef"]。
        # 必须先基于原始 slot（仍为 dict）计算 slotDef，再把 slot 字符串化——
        # 否则 _slot_id 已把 slot 覆盖成 "panel:main"/"float:..." 字符串，
        # _slot_def 会误走「旧字符串声明」分支把 panel/float 归成 fixed。
        p["slotDef"] = _slot_def(p)
        p["slot"] = _slot_id(p)
        plugins.append(p)
    return {
        "ui_mode": str(get_global_settings().get("ui_mode") or "normal"),
        "plugins": plugins,
        # 最左图标栏持久化状态（stage 0=收起 1=仅图标 2=图标+名称 + 各插件隐藏开关 + 白条透明度）
        "rail": stored_cfg.get("rail") or {"stage": 1, "hidden": {}, "opacity": 1},
        # 宿主固有中栏容器配置（透明度/默认宽度），存于 plugins['panel-container']
        "panelContainer": stored.get("panel-container") or {},
    }


def _plugin_backend_info(plugin_dir: str) -> dict | None:
    """探测插件是否自带后端：有 server/server.js 则报告 kind='npm'。"""
    server_js = os.path.join(plugin_dir, "server", "server.js")
    if os.path.isfile(server_js):
        return {"kind": "npm"}
    return None


@router.post("/plugin-rpc/{plugin_id}/{handler}")
def api_webmin_plugin_rpc(plugin_id: str, handler: str, body: dict):
    """调用插件自带的后端子进程 handler（RPC）。body: { payload?, timeout? }。"""
    if not plugin_id or not handler or any(c in plugin_id for c in ("/", "\\", "..")):
        raise HTTPException(status_code=400, detail="非法的参数")
    payload = (body or {}).get("payload") or {}
    timeout = float((body or {}).get("timeout") or 30.0)
    plugin_dir = _resolve_plugin_dir(plugin_id)
    if plugin_dir is None:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_id} 不存在")
    try:
        result = plugin_runtime.rpc_plugin(
            plugin_id, plugin_dir, handler, payload, timeout=timeout
        )
    except plugin_runtime.PluginProcessError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"status": "ok", "result": result}


def _resolve_plugin_dir(plugin_id: str) -> str | None:
    """返回插件所在目录（用户目录优先，内置次之）。"""
    for root in (USER_PLUGIN_ROOT, BUILTIN_PLUGIN_ROOT):
        d = os.path.join(root, plugin_id)
        if os.path.isdir(d):
            return d
    return None


@router.get("/config")
def api_webmin_get_config():
    """读取插件配置：{ "plugins": { plugin_id: config } }。"""
    return _load_webmin_config()


@router.put("/config")
def api_webmin_put_config(body: dict):
    """整体覆写插件配置 + 可选的图标栏状态（前端做默认值合并后提交）。"""
    new_plugins = (
        body.get("plugins")
        if isinstance(body, dict) and isinstance(body.get("plugins"), dict)
        else {}
    )
    cfg = {"plugins": new_plugins}
    if isinstance(body, dict) and isinstance(body.get("rail"), dict):
        try:
            stage = int(body["rail"].get("stage"))
        except (TypeError, ValueError):
            stage = 1
        try:
            opacity = float(body["rail"].get("opacity"))
        except (TypeError, ValueError):
            opacity = 1
        cfg["rail"] = {
            "stage": stage if 0 <= stage <= 2 else 1,
            "opacity": max(0.0, min(1.0, opacity)),
            "hidden": (
                body["rail"].get("hidden")
                if isinstance(body["rail"].get("hidden"), dict)
                else {}
            ),
        }
    _save_webmin_config(cfg)
    return {"status": "ok"}


@router.post("/plugin/{plugin_id}/delete")
def api_webmin_delete_plugin(plugin_id: str):
    """删除用户插件：把 ~/.purrcat/webmin-plugins/{id} 移动为 <id>.trash（可恢复），内置拒绝。"""
    if not plugin_id or any(c in plugin_id for c in ("/", "\\", "..")):
        raise HTTPException(status_code=400, detail="非法的插件 id")
    target = os.path.join(USER_PLUGIN_ROOT, plugin_id)
    builtin_target = os.path.join(BUILTIN_PLUGIN_ROOT, plugin_id)
    if not os.path.isdir(target):
        if os.path.isdir(builtin_target):
            raise HTTPException(status_code=403, detail="内置插件不可删除")
        raise HTTPException(status_code=404, detail=f"插件 {plugin_id} 不存在")
    trash = os.path.join(USER_PLUGIN_ROOT, f"{plugin_id}.trash")
    if os.path.exists(trash):
        shutil.rmtree(trash, ignore_errors=True)
    plugin_runtime.stop(plugin_id)  # 先停后端的子进程，再移动目录
    shutil.move(target, trash)
    return {"status": "ok", "deleted": plugin_id}


@router.post("/wallpaper")
def api_webmin_import_wallpaper(body: dict):
    """把用户选择的本地壁纸复制进托管目录，返回可访问的 URL。body: { path }。"""
    src = str((body or {}).get("path") or "")
    if not src or not os.path.isfile(src):
        raise HTTPException(status_code=404, detail="壁纸文件不存在")
    ext = os.path.splitext(src)[1].lower()
    if ext not in _WALLPAPER_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的壁纸格式: {ext}")
    os.makedirs(WALLPAPER_DIR, exist_ok=True)
    digest = hashlib.md5(os.path.abspath(src).encode("utf-8")).hexdigest()[:12]
    filename = f"wallpaper_{digest}{ext}"
    dest = os.path.join(WALLPAPER_DIR, filename)
    if not os.path.exists(dest):
        shutil.copy2(src, dest)
    return {
        "status": "ok",
        "filename": filename,
        "url": f"/api/webmin/wallpaper/{filename}",
    }


@router.get("/wallpaper/{filename}")
def api_webmin_serve_wallpaper(filename: str):
    """静态托管壁纸文件（沙箱到 WALLPAPER_DIR 防穿越）。"""
    if not filename or any(c in filename for c in ("/", "\\", "..")):
        raise HTTPException(status_code=400, detail="非法的文件名")
    target = os.path.join(WALLPAPER_DIR, filename)
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="壁纸不存在")
    return FileResponse(target)


@router.get("/ref/graphs")
def api_webmin_ref_graphs():
    """枚举可用于引用的 graph（~/.purrcat/graph 下每个含 graph.json 的目录）。"""
    if not os.path.isdir(GRAPHS_DIR):
        return []
    names = []
    for name in os.listdir(GRAPHS_DIR):
        d = os.path.join(GRAPHS_DIR, name)
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, "graph.json")):
            names.append(name)
    return names


@router.get("/plugin/{plugin_id}/{path:path}")
def api_webmin_plugin(plugin_id: str, path: str):
    """按路径读取插件目录内静态文件；未指定路径时回退到 descriptor 的 entry。"""
    target = _resolve_plugin_file(plugin_id, path)
    # 若只请求插件根路径或未命中文件，尝试拉取 entry 作为默认文档
    if target is None:
        desc = _merge_plugins()
        found = next((d for d in desc if d["id"] == plugin_id), None)
        if found:
            entry = str(found.get("entry") or "index.html")
            target = _resolve_plugin_file(plugin_id, entry)
    if target is None:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_id} 资源不存在")
    return FileResponse(target)


@router.post("/action")
def api_webmin_action(payload: dict):
    """动作协议：宿主/插件通过 callAction(actionId, payload) 调用的后端副作用动作。"""
    action_id = str(payload.get("actionId") or "")
    data = payload.get("payload") or {}
    handler = _ACTION_HANDLERS.get(action_id)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"未注册的动作: {action_id}")
    try:
        handler(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"动作 {action_id} 执行失败: {e}")
    return (
        {"status": "ok", "restart": True}
        if action_id == "switch_to_normal"
        else {"status": "ok"}
    )

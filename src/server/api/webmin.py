"""极简模式（web-minimal）插件 API。

与现有 React UI 完全独立：宿主为纯静态页面（ui/web-minimal），它通过本路由
获取插件清单、按需读取插件静态文件（热插拔），以及执行约定的后端动作协议
（callAction）。

插件来源：
  - 内置四件套：{BASE_DIR}/ui/web-minimal/plugins/builtin/*（随 App 分发，只读）
  - 沙盒插件：  {AGENT_VM_DIR}/ui-plugin/*（Agent 在沙盒里开发的插件，同名 id 可覆盖内置）
  - 用户插件：  {PURRCAT_DIR}/webmin-plugins/*（热插拔，优先级最高，同名 id 覆盖前两者）

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
    AGENT_VM_DIR,
    BASE_DIR,
    PURRCAT_DIR,
    GRAPHS_DIR,
    SESSIONS_DIR,
    get_global_settings,
    save_global_setting,
)

router = APIRouter(prefix="/api/webmin", tags=["WebMinimal"])

# 内置插件根目录（随 App 分发，只读）
BUILTIN_PLUGIN_ROOT = os.path.join(BASE_DIR, "ui", "web-minimal", "plugins", "builtin")
# 沙盒插件根目录（Agent 的插件开发区，位于 AgentVM 内，Agent 可直接读写）
SANDBOX_PLUGIN_ROOT = os.path.join(AGENT_VM_DIR, "ui-plugin")
# 用户插件根目录（热插拔）
USER_PLUGIN_ROOT = os.path.join(PURRCAT_DIR, "webmin-plugins")
# 三个插件根目录，按优先级从高到低（同名 id 先命中者生效）
PLUGIN_ROOTS = (USER_PLUGIN_ROOT, SANDBOX_PLUGIN_ROOT, BUILTIN_PLUGIN_ROOT)
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


AREA_PANEL = "panel"
AREA_PET = "pet"  # 自由浮窗：可任意摆放/拖拽缩放，不干扰其它插件
AREA_POPUP = "popup"  # 模态弹窗：与设置中心同级，遮罩铺满主区（仅白条与设置中心可操作）


def _plugin_area(p: dict) -> str:
    """插件声明所在区域——area 是插件声明的唯一维度。

    区域取值：rail / sidebar / input / background / conversation /
    panel-container / panel / pet / popup。字符串声明直接视作区域。
    """
    pid = str(p.get("id") or "")
    slot = p.get("slot")
    if isinstance(slot, dict):
        return str(slot.get("area") or pid)
    return str(slot or pid)


def _area_behavior(area: str) -> str:
    """区域 → 宿主行为类别（不写进 plugin.json，由宿主按区域内置）。

    panel=入驻容器抽屉；pet=自由浮窗（可拖拽缩放）；popup=模态弹窗
    （遮罩铺满主区，白条与设置中心仍可操作）；其余区域=锚定单例。
    """
    if area == AREA_PANEL:
        return "panel"
    if area == AREA_PET:
        return "float"
    if area == AREA_POPUP:
        return "modal"
    return "fixed"


def _slot_id(p: dict) -> str:
    """插件的 slot id（宿主分组键 / 单例状态键 / 设置面板展示用）。

    panel 内容插件共享宿主单例容器固定键 ``panel``；pet/popup 每插件独立键
    ``float:{plugin_id}`` / ``modal:{plugin_id}``；其余区域以 area 本身为键。
    """
    area = _plugin_area(p)
    if area == AREA_PANEL:
        return "panel"
    if area == AREA_PET:
        return "float:" + str(p.get("id") or "")
    if area == AREA_POPUP:
        return "modal:" + str(p.get("id") or "")
    return area


def _slot_def(p: dict) -> dict:
    """归一化插件的 slot 声明：area 为唯一维度，行为类别 type 由宿主按区域推导。

    fixed（锚定单例，同 area 只取第一个生效）、panel（入驻宿主系统级单例容器
    panel-container，经容器右上角抽屉切换显示）、float（pet 自由浮窗，多插件各自
    独立、可拖拽可缩放）与 modal（popup 模态弹窗，遮罩铺满主区、尺寸随窗口自适应）。
    """
    area = _plugin_area(p)
    out = {"type": _area_behavior(area), "area": area}
    slot = p.get("slot")
    if isinstance(slot, dict):
        # float/modal 可选声明默认尺寸；size 的 w/h 可为数字（px）或 CSS 长度串。
        # center 仅对 float（pet 自由浮窗）有意义：modal（popup）天然居中。
        # {"area": "pet", "size": {"w": 300, "h": 360}, "center": true}
        # {"area": "popup", "size": {"w": "min(1040px, 96vw)", "h": "86vh"}}
        if isinstance(slot.get("size"), dict):
            out["size"] = slot["size"]
        if slot.get("center"):
            out["center"] = True
    return out


def _merge_plugins():
    """内置插件为底，沙盒与用户同名插件依次覆盖（下重上）。返回按 slot 分组的列表。"""
    merged = _scan_plugins(BUILTIN_PLUGIN_ROOT)
    merged.update(_scan_plugins(SANDBOX_PLUGIN_ROOT))  # 沙盒（Agent 开发）覆盖内置
    merged.update(_scan_plugins(USER_PLUGIN_ROOT))  # 用户插件优先级最高
    plugins = list(merged.values())
    ordered = [
        "sidebar",
        "input",
        "background",
        "conversation",
        "panel",
        "pet",
        "popup",
    ]
    plugins.sort(
        key=lambda p: (
            ordered.index(_slot_id(p)) if _slot_id(p) in ordered else 999,
            p.get("name", ""),
        )
    )
    return plugins


def _resolve_plugin_file(plugin_id: str, rel_path: str) -> str | None:
    """在用户/沙盒/内置插件根目录中定位插件文件，沙箱到插件目录内防路径穿越。"""
    rel_path = rel_path.replace("\\", "/").lstrip("/")
    for root in PLUGIN_ROOTS:
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
        # 否则 _slot_id 已把 slot 覆盖成 "panel"/"float:..." 字符串，
        # _slot_def 会把 float 的独立键误当成区域名来推导行为。
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
        # 单例槽当前选中的插件（fixed: {area: plugin_id}；panel 容器: {panel: plugin_id|'__none__'}），
        # 重启后据此恢复用户上次的选择，而不是回退到声明顺序第一个
        "active": stored_cfg.get("active") or {},
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
    """返回插件所在目录（用户目录优先，其次沙盒，最后内置）。"""
    for root in PLUGIN_ROOTS:
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
    """按分节更新宿主配置（plugins / rail / active），未提供的分节保持原值。

    前端每次只提交自己修改的分节（例如滑块只提交 plugins），避免局部保存把
    其他分节（图标栏状态、单例槽选中项）意外清空。
    """
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")
    cfg = _load_webmin_config()
    if isinstance(body.get("plugins"), dict):
        cfg["plugins"] = body["plugins"]
    if isinstance(body.get("rail"), dict):
        rail = body["rail"]
        try:
            stage = int(rail.get("stage"))
        except (TypeError, ValueError):
            stage = 1
        try:
            opacity = float(rail.get("opacity"))
        except (TypeError, ValueError):
            opacity = 1
        cfg["rail"] = {
            "stage": stage if 0 <= stage <= 2 else 1,
            "opacity": max(0.0, min(1.0, opacity)),
            "hidden": (
                rail.get("hidden") if isinstance(rail.get("hidden"), dict) else {}
            ),
        }
    if isinstance(body.get("active"), dict):
        # 单例槽（fixed 各 area 与共享的 panel 容器）当前选中的插件 id
        cfg["active"] = {
            str(k): str(v)
            for k, v in body["active"].items()
            if isinstance(v, (str, int)) and str(v)
        }
    _save_webmin_config(cfg)
    return {"status": "ok"}


@router.post("/plugin/{plugin_id}/delete")
def api_webmin_delete_plugin(plugin_id: str):
    """删除插件：用户/沙盒插件移动为各自根目录下的 <id>.trash（可恢复），内置拒绝。"""
    if not plugin_id or any(c in plugin_id for c in ("/", "\\", "..")):
        raise HTTPException(status_code=400, detail="非法的插件 id")
    for root in (USER_PLUGIN_ROOT, SANDBOX_PLUGIN_ROOT):
        target = os.path.join(root, plugin_id)
        if not os.path.isdir(target):
            continue
        trash = os.path.join(root, f"{plugin_id}.trash")
        if os.path.exists(trash):
            shutil.rmtree(trash, ignore_errors=True)
        plugin_runtime.stop(plugin_id)  # 先停后端的子进程，再移动目录
        shutil.move(target, trash)
        return {"status": "ok", "deleted": plugin_id}
    if os.path.isdir(os.path.join(BUILTIN_PLUGIN_ROOT, plugin_id)):
        raise HTTPException(status_code=403, detail="内置插件不可删除")
    raise HTTPException(status_code=404, detail=f"插件 {plugin_id} 不存在")


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


@router.get("/session-paradigm/{session_id}")
def api_webmin_session_paradigm(session_id: str):
    """读取某会话当前绑定的 Agent Loop（paradigm）；空串表示使用默认 PARADIGM。

    只读端点：供极简模式的输入框回显当前 Mode，不改动任何现有 /api/* 行为。
    """
    if not session_id or any(c in session_id for c in ("/", "\\", "..")):
        raise HTTPException(status_code=400, detail="非法的会话 id")
    meta_path = os.path.join(SESSIONS_DIR, session_id, "meta.json")
    paradigm = ""
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            paradigm = str((json.load(f) or {}).get("paradigm") or "")
    except Exception:
        paradigm = ""
    return {"paradigm": paradigm}


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

"""极简模式（web-minimal）插件系统 API。

极简模式（web-minimal）宿主为纯静态页面（ui/web-minimal），它通过本路由
获取插件清单、按需读取插件静态文件（热插拔）、持久化宿主配置，并转发插件
自带后端的 RPC 调用。

插件来源：
  - 内置四件套：{BASE_DIR}/ui/web-minimal/plugins/builtin/*（随 App 分发，只读）
  - 沙盒插件：  {AGENT_VM_DIR}/ui-plugin/*（Agent 在沙盒里开发的插件，同名 id 可覆盖内置）
  - 用户插件：  {PURRCAT_DIR}/webmin-plugins/*（热插拔，优先级最高，同名 id 覆盖前两者）

互不干扰原则：本文件只新增路由，不修改任何现有 /api/* 路由行为。
"""

import os
import shutil
import hashlib

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.server.api import plugin_runtime, webmin_manifest, webmin_scan
from src.server.api.common import is_unsafe_name
from src.utils._fs import read_json
from src.utils.config import (
    AGENT_VM_DIR,
    BASE_DIR,
    PURRCAT_DIR,
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
# plugin.json 的 root 字段（插件期望放置的位置）取值 → 对应的实际根目录
ROOT_TO_DIR = {
    "user": USER_PLUGIN_ROOT,
    "sandbox": SANDBOX_PLUGIN_ROOT,
    "builtin": BUILTIN_PLUGIN_ROOT,
}
# dependency 允许的依赖类型：技能 / 其它 UI 插件 / MCP / AgentLoop(paradigm) / 传感器 / 图谱
DEP_TYPES = ("skill", "plugin", "mcp", "agentloop", "sensor", "graph")
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
    return webmin_manifest.is_builtin(plugin_dir, BUILTIN_PLUGIN_ROOT)


def _plugin_origin(plugin_dir: str) -> str:
    """插件实际所在的根（回填 plugin.json 的 root）：user / sandbox / builtin。"""
    return webmin_manifest.plugin_origin(plugin_dir, ROOT_TO_DIR)


# 宿主共享运行时清单：/minimal/shared/manifest.json（按版本目录发布，路径不可变）
SHARED_MANIFEST_PATH = os.path.join(
    BASE_DIR, "ui", "web-minimal", "shared", "manifest.json"
)
_SHARED_CACHE = {"mtime": None, "data": {}}


def _shared_catalog() -> dict:
    """读取共享运行时清单，返回 {name: {version, base}}。失败时返回空表。"""
    try:
        mtime = os.path.getmtime(SHARED_MANIFEST_PATH)
        if _SHARED_CACHE["mtime"] == mtime:
            return _SHARED_CACHE["data"]
        raw = read_json(SHARED_MANIFEST_PATH)
        if raw is None:
            return {}
        data = webmin_manifest.normalize_shared_catalog(raw)
        _SHARED_CACHE["mtime"] = mtime
        _SHARED_CACHE["data"] = data
        return data
    except Exception:
        return {}


def _merge_plugins():
    """内置插件为底，沙盒与用户同名插件依次覆盖（下重上）。返回按 slot 分组的列表。"""
    merged = webmin_scan.scan_plugin_roots(
        (BUILTIN_PLUGIN_ROOT, SANDBOX_PLUGIN_ROOT, USER_PLUGIN_ROOT)
    )
    return webmin_manifest.sort_plugins(list(merged.values()))


@router.get("/manifest")
def api_webmin_manifest():
    """返回当前已扫描到的全部插件列表（未新增插件即热插拔可感知）。

    每条插件附 configSchema（插件自声明）与 config（webminConfig 中的已存值），
    有效配置 = configSchema 默认值 ∪ config 覆盖；backend 表明该插件是否自带后端。
    另附 root（声明的期望放置位置：builtin/sandbox/user）、origin（后端回填的实际
    所在根）、rootOk（两者是否一致）与 dependency（归一化的依赖清单）。
    """
    stored_cfg = _load_webmin_config()
    stored = stored_cfg.get("plugins") or {}
    catalog = _shared_catalog()
    plugins = []
    for p in _merge_plugins():
        plugins.append(
            webmin_manifest.build_manifest_entry(
                p,
                stored.get(p["id"]),
                catalog=catalog,
                dep_types=DEP_TYPES,
                builtin=_is_builtin(p.get("dir") or ""),
                backend=webmin_scan.plugin_backend_info(p.get("dir") or ""),
                origin=_plugin_origin(p.get("dir") or ""),
                root_to_dir=ROOT_TO_DIR,
            )
        )
    return {
        "plugins": plugins,
        # 宿主共享运行时清单：{name: {version, base}}，供插件按版本目录引用
        "shared": catalog,
        # 最左图标栏持久化状态（stage 0=仅图标 1=图标+文字 + 各插件隐藏开关 + 白条透明度）
        "rail": stored_cfg.get("rail") or {"stage": 0, "hidden": {}, "opacity": 1},
        # 宿主固有中栏容器配置（透明度/默认宽度），存于 plugins['panel-container']
        "panelContainer": stored.get("panel-container") or {},
        # 单例槽当前选中的插件（fixed: {area: plugin_id}；panel 容器: {panel: plugin_id|'__none__'}），
        # 重启后据此恢复用户上次的选择，而不是回退到声明顺序第一个
        "active": stored_cfg.get("active") or {},
    }


@router.post("/plugin-rpc/{plugin_id}/{handler}")
def api_webmin_plugin_rpc(plugin_id: str, handler: str, body: dict):
    """调用插件自带的后端子进程 handler（RPC）。body: { payload?, timeout? }。"""
    if not plugin_id or not handler or is_unsafe_name(plugin_id):
        raise HTTPException(status_code=400, detail="非法的参数")
    payload = (body or {}).get("payload") or {}
    timeout = float((body or {}).get("timeout") or 30.0)
    plugin_dir = webmin_scan.resolve_plugin_dir(plugin_id, PLUGIN_ROOTS)
    if plugin_dir is None:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_id} 不存在")
    try:
        result = plugin_runtime.rpc_plugin(
            plugin_id,
            plugin_dir,
            handler,
            payload,
            timeout=timeout,
            allow_install=not _is_builtin(plugin_dir),
        )
    except plugin_runtime.PluginProcessError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"status": "ok", "result": result}


@router.post("/plugin-backend/{plugin_id}/{action}")
def api_webmin_plugin_backend(plugin_id: str, action: str):
    """插件后端子进程生命周期：start / stop / restart / status。

    宿主在面板标签打开时 start、关闭时 stop，使插件后端随标签存活，
    因此改完 ``server/server.js`` 只要关掉再打开标签即可生效，无需重启 PurrCat。
    """
    if is_unsafe_name(plugin_id):
        raise HTTPException(status_code=400, detail="非法的插件 id")
    if action not in ("start", "stop", "restart", "status"):
        raise HTTPException(status_code=400, detail=f"未知操作: {action}")
    if action == "status":
        return {"status": "ok", "running": plugin_runtime.is_running(plugin_id)}
    if action in ("stop", "restart"):
        plugin_runtime.stop(plugin_id)
        if action == "stop":
            return {"status": "ok", "running": False}
    plugin_dir = webmin_scan.resolve_plugin_dir(plugin_id, PLUGIN_ROOTS)
    if plugin_dir is None:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_id} 不存在")
    try:
        info = plugin_runtime.start(
            plugin_id, plugin_dir, allow_install=not _is_builtin(plugin_dir)
        )
    except plugin_runtime.PluginProcessError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"status": "ok", **info}


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
        cfg["rail"] = webmin_manifest.sanitize_rail(body["rail"])
    if isinstance(body.get("active"), dict):
        # 单例槽（fixed 各 area 与共享的 panel 容器）当前选中的插件 id
        cfg["active"] = webmin_manifest.normalize_active(body["active"])
    _save_webmin_config(cfg)
    return {"status": "ok"}


@router.post("/plugin/{plugin_id}/delete")
def api_webmin_delete_plugin(plugin_id: str):
    """删除插件：用户/沙盒插件移动为各自根目录下的 <id>.trash（可恢复），内置拒绝。"""
    if is_unsafe_name(plugin_id):
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
    if is_unsafe_name(filename):
        raise HTTPException(status_code=400, detail="非法的文件名")
    target = os.path.join(WALLPAPER_DIR, filename)
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="壁纸不存在")
    return FileResponse(target)


@router.get("/plugin/{plugin_id}/{path:path}")
def api_webmin_plugin(plugin_id: str, path: str):
    """按路径读取插件目录内静态文件；未指定路径时回退到 descriptor 的 entry。"""
    target = webmin_scan.resolve_plugin_file(plugin_id, path, PLUGIN_ROOTS)
    # 若只请求插件根路径或未命中文件，尝试拉取 entry 作为默认文档
    if target is None:
        desc = _merge_plugins()
        found = next((d for d in desc if d["id"] == plugin_id), None)
        if found:
            entry = str(found.get("entry") or "index.html")
            target = webmin_scan.resolve_plugin_file(plugin_id, entry, PLUGIN_ROOTS)
    if target is None:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_id} 资源不存在")
    return FileResponse(target)


@router.get("/plugin-dir/{plugin_id}/{path:path}")
def api_webmin_plugin_dir(plugin_id: str, path: str = ""):
    """列出插件目录内某一层的子项（仅名字与是否目录），供插件自动扫描自身数据目录。

    只返回一层、不含文件内容；沙箱到插件目录内防穿越。
    """
    target = webmin_scan.resolve_plugin_subdir(plugin_id, path, PLUGIN_ROOTS)
    if target is None:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_id} 目录不存在")
    entries = []
    try:
        for name in sorted(os.listdir(target)):
            if name.startswith("."):
                continue
            entries.append(
                {"name": name, "isDir": os.path.isdir(os.path.join(target, name))}
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取目录失败: {e}")
    return {"path": path, "entries": entries}

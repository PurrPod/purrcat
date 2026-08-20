import json
import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Body

# 👇 引入全局的 agent_manager
from src.agent.manager import manager as agent_manager

from src.utils.config import (
    APP_CONFIG_PATH,
    FILE_CONFIG_PATH,
    MCP_CONFIG_PATH,
    MODEL_CONFIG_PATH,
    SENSOR_CONFIG_PATH,
    AGENT_CORE_DIR,
    GLOBAL_CONFIG_FILE,
    CRON_FILE,
    get_app_config,
    get_file_config,
    get_mcp_config,
    get_model_config,
    get_sensor_config,
    is_data_root_configured,
    save_global_setting,
    PURRCAT_DIR,
    DATA_ROOT,
    BASE_DIR,
)

router = APIRouter(prefix="/api/config", tags=["Configuration"])


def _save_json_file(file_path: str, data: Dict[str, Any]) -> bool:
    """通用的 JSON 写入方法"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Config API] 保存配置文件失败 {file_path}: {e}")
        return False


# ── Model Config ──
@router.get("/model")
def api_get_model_config():
    return get_model_config()


@router.put("/model")
def api_update_model_config(config: Dict[str, Any]):
    if _save_json_file(MODEL_CONFIG_PATH, config):
        # 👇 保存 JSON 成功后，立刻通知内存中的 Agent 热重载！
        agent_manager.reload_model()
        return {
            "status": "ok",
            "message": "Model config updated and reloaded successfully",
        }
    raise HTTPException(status_code=500, detail="Failed to save model config")


# ── Sensor Config ──
@router.get("/sensor")
def api_get_sensor_config():
    return get_sensor_config()


@router.put("/sensor")
def api_update_sensor_config(config: Dict[str, Any]):
    if _save_json_file(SENSOR_CONFIG_PATH, config):
        return {"status": "ok", "message": "Sensor config updated successfully"}
    raise HTTPException(status_code=500, detail="Failed to save sensor config")


@router.post("/sensor/reload")
def api_reload_sensor_manager():
    """停止所有运行中的 Sensor 进程，并重新读取配置拉起启用状态的 Sensor"""
    try:
        from src.sensor.manager import get_manager

        manager = get_manager()
        manager.stop_all()  # 杀死旧进程
        manager.load_and_start_all()  # 重新读取 activate_sensor.json 并拉起
        return {"status": "ok", "message": "Sensors reloaded successfully"}
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"热重启失败: {str(e)}")


# ── File Config ──
@router.get("/file")
def api_get_file_config():
    return get_file_config()


@router.put("/file")
def api_update_file_config(config: Dict[str, Any]):
    if _save_json_file(FILE_CONFIG_PATH, config):
        return {"status": "ok", "message": "File config updated successfully"}
    raise HTTPException(status_code=500, detail="Failed to save file config")


# ── MCP Config ──
@router.get("/mcp")
def api_get_mcp_config():
    return get_mcp_config()


@router.put("/mcp")
def api_update_mcp_config(config: Dict[str, Any]):
    if _save_json_file(MCP_CONFIG_PATH, config):
        return {"status": "ok", "message": "MCP config updated successfully"}
    raise HTTPException(status_code=500, detail="Failed to save MCP config")


# ── App Config ──
@router.get("/app")
def api_get_app_config():
    return get_app_config()


@router.put("/app")
def api_update_app_config(config: Dict[str, Any]):
    if _save_json_file(APP_CONFIG_PATH, config):
        return {"status": "ok", "message": "App config updated successfully"}
    raise HTTPException(status_code=500, detail="Failed to save app config")


# ── Markdown Files (SOUL.md / GOAL.md) ──
@router.get("/markdown/{filename}")
def api_get_markdown_file(filename: str):
    # 限制只允许读取 SOUL 和 GOAL，防止任意路径穿越漏洞
    if filename not in ["SOUL", "GOAL"]:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # 引入 config 中定义好的 AGENT_CORE_DIR (.purrcat/core/)
    file_path = os.path.join(AGENT_CORE_DIR, f"{filename}.md")

    # 如果文件不存在，返回空内容防报错
    if not os.path.exists(file_path):
        return {"content": ""}

    with open(file_path, "r", encoding="utf-8") as f:
        return {"content": f.read()}


@router.put("/markdown/{filename}")
def api_update_markdown_file(filename: str, payload: dict = Body(...)):
    if filename not in ["SOUL", "GOAL"]:
        raise HTTPException(status_code=400, detail="Invalid filename")

    content = payload.get("content", "")

    # 同样定位到 AGENT_CORE_DIR (.purrcat/core/)
    file_path = os.path.join(AGENT_CORE_DIR, f"{filename}.md")

    # 自动创建 core 目录以防万一
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "ok", "message": f"{filename}.md saved successfully"}
    except Exception as e:
        print(f"Failed to save {filename}.md: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save {filename}.md")


# ── Info Config (Skills & Workshops) ──
@router.get("/info")
def api_get_info_config():
    """读取 .purrcat/core/info.json，提供 skills 和 workshops 列表"""
    try:
        file_path = os.path.join(AGENT_CORE_DIR, "info.json")
        if not os.path.exists(file_path):
            return {"skills": [], "workshops": []}
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Config API] 读取 info.json 失败: {e}")
        return {"skills": [], "workshops": []}


# ── 数据根目录（settings.json 内部管理，UI 无全局设置编辑页） ──
# 数据根目录下需要整体搬迁的大型数据子目录
LARGE_DATA_SUBDIRS = ("agent_vm", "embedding")


def _validate_data_root(value: str) -> str:
    """校验数据根目录候选路径，非法直接抛 HTTPException"""
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail="数据目录不能为空")
    value = value.strip()

    if not os.path.isabs(value):
        raise HTTPException(
            status_code=400, detail="数据目录必须是绝对路径，如 D:\\purrcat_data"
        )

    # 拒绝磁盘根目录，避免 agent_vm 等直接散落在盘符根下
    drive, _ = os.path.splitdrive(value)
    if drive and os.path.normpath(value) == os.path.normpath(drive + os.sep):
        raise HTTPException(
            status_code=400, detail="不能直接选择磁盘根目录，请选择盘下的一个子目录"
        )
    return os.path.normpath(value)


# ── 首次启动数据盘引导 ──
@router.get("/setup-status")
def api_setup_status():
    """首启引导用：数据盘是否已配置（配置过就不再弹引导）"""
    configured = is_data_root_configured()
    return {"configured": configured, "data_root": DATA_ROOT if configured else ""}


@router.post("/setup-data-root")
def api_setup_data_root(payload: Dict[str, Any] = Body(default={})):
    """首次启动设置数据盘（仅首次引导使用；后续变更走 /change-data-root）"""
    if is_data_root_configured():
        raise HTTPException(
            status_code=409, detail="数据盘已配置，变更请使用配置中心的数据根目录入口"
        )

    value = _validate_data_root((payload or {}).get("data_root", ""))

    if not save_global_setting("data_root", value):
        raise HTTPException(status_code=500, detail="保存数据盘配置失败")

    print(f"[Config API] 首次启动数据盘已设置: {value}（重启后生效）")
    return {"status": "ok", "data_root": value, "message": "数据盘设置成功，重启后生效"}


@router.post("/change-data-root")
def api_change_data_root(payload: Dict[str, Any] = Body(default={})):
    """随时更改数据根目录：搬迁旧根目录下的大型数据到新位置，落盘配置，前端随后重启生效"""
    import shutil

    new_root = _validate_data_root((payload or {}).get("data_root", ""))
    old_root = os.path.normpath(DATA_ROOT)

    if new_root == old_root:
        raise HTTPException(
            status_code=400, detail=f"新目录与当前数据根目录相同：{old_root}"
        )

    # 新旧目录互为父子时搬迁会自嵌套，直接拒绝
    if old_root.startswith(new_root + os.sep) or new_root.startswith(old_root + os.sep):
        raise HTTPException(
            status_code=400,
            detail="新目录不能位于当前数据根目录内部，也不能是它的父目录",
        )

    # 搬迁大型数据子目录（agent_vm / embedding）
    moved = []
    try:
        os.makedirs(new_root, exist_ok=True)
        for name in LARGE_DATA_SUBDIRS:
            src = os.path.join(old_root, name)
            if not os.path.exists(src):
                continue
            dst = os.path.join(new_root, name)
            if os.path.exists(dst):
                raise HTTPException(
                    status_code=409,
                    detail=f"目标位置已存在同名子目录：{dst}，请先清理后重试",
                )
            shutil.move(src, dst)
            moved.append(name)
    except HTTPException:
        _rollback_moved_dirs(new_root, old_root, moved)
        raise
    except Exception as e:
        _rollback_moved_dirs(new_root, old_root, moved)
        raise HTTPException(status_code=500, detail=f"数据搬迁失败: {str(e)}")

    if not save_global_setting("data_root", new_root):
        _rollback_moved_dirs(new_root, old_root, moved)
        raise HTTPException(status_code=500, detail="保存数据盘配置失败")

    print(
        f"[Config API] 数据根目录已切换: {old_root} -> {new_root}"
        f"（搬迁: {', '.join(moved) if moved else '无'}，重启后生效）"
    )
    return {
        "status": "ok",
        "data_root": new_root,
        "moved": moved,
        "message": "数据已搬迁并落盘配置，重启后生效",
    }


def _rollback_moved_dirs(new_root: str, old_root: str, moved: list):
    """搬迁中途失败时，把已搬走的子目录挪回旧根目录，避免半迁移状态"""
    import shutil

    for name in moved:
        src = os.path.join(new_root, name)
        dst = os.path.join(old_root, name)
        try:
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.move(src, dst)
        except Exception:
            pass


# ── Cron Config (cron.json) ──
@router.get("/cron")
def api_get_cron_config():
    if not os.path.exists(CRON_FILE):
        return {"jobs": []}
    try:
        with open(CRON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"jobs": []}


@router.put("/cron")
def api_update_cron_config(config: Dict[str, Any]):
    if _save_json_file(CRON_FILE, config):
        return {"status": "ok", "message": "Cron config updated successfully"}
    raise HTTPException(status_code=500, detail="Failed to save cron config")


# ── Paths Meta (前端展示用：当前实际生效的各数据目录) ──
@router.get("/meta")
def api_get_config_meta():
    """返回当前正在生效的路径常量，便于前端显示给用户做参考。"""
    return {
        "PURRCAT_DIR": PURRCAT_DIR,  # ~/.purrcat（配置类目录，固定）
        "DATA_ROOT": DATA_ROOT,  # 大型数据根目录（读 settings.json data_root，重启生效）
        "BASE_DIR": BASE_DIR,  # 程序只读目录（打包后是 _MEIPASS）
        "settings_path": str(GLOBAL_CONFIG_FILE),
        "cron_path": CRON_FILE,
    }

"""Config API 的服务编排（SPEC-020）。

集中 Sensor 配置与运行时控制、数据根迁移、部署与磁盘维护；
路由层只做参数透传与异常转 HTTP，业务顺序和文案保持原样。
"""

import os
import shutil
import subprocess
from datetime import datetime
from typing import Any, Dict

from fastapi import HTTPException

from src.server.api import common
from src.server.api.config_validation import (
    normalize_sandbox_registry,
    validate_data_root,
)
from src.utils.config import (
    DATA_ROOT,
    SENSOR_CONFIG_PATH,
    SENSOR_EXTENSION_DIR,
    get_global_settings,
    get_sensor_config,
    is_data_root_configured,
    save_global_setting,
)


def _save_sensor_config(config: Dict[str, Any]) -> bool:
    return common.save_json_file(SENSOR_CONFIG_PATH, config, log_prefix="[Config API]")


# ── Sensor 配置读写与运行时控制 ──
def save_sensor_config(config: Dict[str, Any]) -> dict:
    if _save_sensor_config(config):
        return {"status": "ok", "message": "Sensor config updated successfully"}
    raise HTTPException(status_code=500, detail="Failed to save sensor config")


def reload_sensors() -> dict:
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


def list_running_sensors() -> dict:
    """列出当前运行中的 Sensor 进程（配置页「后台进程」展示用）"""
    try:
        from src.sensor.manager import get_manager

        return {"running": get_manager().list_running()}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"读取 Sensor 运行状态失败: {str(e)}"
        )


def stop_sensor(name: str) -> dict:
    """停止指定 Sensor：先把配置置为 enabled=false（防 watchdog 复拉），再整树击杀进程"""
    cfg = get_sensor_config()
    if isinstance(cfg, dict) and isinstance(cfg.get(name), dict):
        cfg[name]["enabled"] = False
        if not _save_sensor_config(cfg):
            raise HTTPException(status_code=500, detail="禁用配置写入失败，已放弃停止")

    try:
        from src.sensor.manager import get_manager

        stopped = get_manager().stop_sensor(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止 Sensor 失败: {str(e)}")

    message = (
        f"已停止 Sensor '{name}' 并置为 enabled=false"
        if stopped
        else f"Sensor '{name}' 当前没有运行中的进程（已置为 enabled=false）"
    )
    return {"status": "ok", "stopped": stopped, "message": message}


def purge_sensor(name: str) -> dict:
    """彻底删除指定 Sensor（不可恢复）：先从配置移除 → 再杀进程 → 最后删正式 <name>.py。

    顺序很重要：配置项先消失，watchdog 才不会在杀进程后的窗口里把它又拉起来。
    """
    cfg = get_sensor_config()
    if isinstance(cfg, dict) and name in cfg:
        cfg.pop(name, None)
        if not _save_sensor_config(cfg):
            raise HTTPException(status_code=500, detail="配置写入失败，已放弃彻底删除")

    stopped = False
    try:
        from src.sensor.manager import get_manager

        stopped = get_manager().stop_sensor(name)
    except Exception as e:
        print(f"[Config API] 彻底删除时停止 Sensor 失败 {name}: {e}")

    script_path = os.path.join(SENSOR_EXTENSION_DIR, f"{name}.py")
    file_deleted = False
    # 正式目录是 git 仓库：优先 git rm（连带清索引并提交），失败再退化为直接删文件
    if os.path.isdir(os.path.join(SENSOR_EXTENSION_DIR, ".git")):
        try:
            rm = subprocess.run(
                ["git", "rm", "-f", f"{name}.py"],
                cwd=SENSOR_EXTENSION_DIR,
                capture_output=True,
                text=True,
            )
            if rm.returncode == 0:
                file_deleted = True
                subprocess.run(
                    [
                        "git",
                        "commit",
                        "-m",
                        f"purge sensor {name} {datetime.now().strftime('%Y-%m-%d')}",
                    ],
                    cwd=SENSOR_EXTENSION_DIR,
                    capture_output=True,
                    text=True,
                )
        except Exception as e:
            print(f"[Config API] 彻底删除时 git rm 失败 {name}: {e}")
    if not file_deleted and os.path.isfile(script_path):
        try:
            os.remove(script_path)
            file_deleted = True
        except OSError as e:
            raise HTTPException(
                status_code=500, detail=f"删除 {script_path} 失败: {str(e)}"
            )

    message = (
        f"已彻底删除 Sensor '{name}'（进程{'已停止' if stopped else '未在运行'}，"
        f"文件{'已删除' if file_deleted else '不存在'}，配置已移除）"
    )
    return {
        "status": "ok",
        "stopped": stopped,
        "file_deleted": file_deleted,
        "message": message,
    }


def restart_sensor(name: str) -> dict:
    """重启指定 Sensor：先把配置置为 enabled=true（被停止过的是 false，否则 watchdog 不会复拉），
    再整树击杀旧进程并按当前配置重新拉起"""
    cfg = get_sensor_config()
    if not isinstance(cfg, dict) or not isinstance(cfg.get(name), dict):
        raise HTTPException(status_code=404, detail=f"未配置 Sensor '{name}'，无法重启")

    if not cfg[name].get("enabled", False):
        cfg[name]["enabled"] = True
        if not _save_sensor_config(cfg):
            raise HTTPException(status_code=500, detail="启用配置写入失败，已放弃重启")

    try:
        from src.sensor.manager import get_manager

        started = get_manager().restart_sensor(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重启 Sensor 失败: {str(e)}")

    message = (
        f"已重启 Sensor '{name}'（新进程已拉起）"
        if started
        else f"Sensor '{name}' 拉起失败：请检查本地是否存在 {name}.py 以及 uv 是否可用"
    )
    return {"status": "ok", "started": started, "message": message}


# ── 数据根迁移 ──
def setup_data_root(payload: Dict[str, Any]) -> dict:
    """首次启动设置数据盘（仅首次引导使用；后续变更走 /change-data-root）"""
    if is_data_root_configured():
        raise HTTPException(
            status_code=409, detail="数据盘已配置，变更请使用配置中心的数据根目录入口"
        )

    value = validate_data_root((payload or {}).get("data_root", ""))

    if not save_global_setting("data_root", value):
        raise HTTPException(status_code=500, detail="保存数据盘配置失败")

    print(f"[Config API] 首次启动数据盘已设置: {value}（重启后生效）")
    return {"status": "ok", "data_root": value, "message": "数据盘设置成功，重启后生效"}


def change_data_root(payload: Dict[str, Any]) -> dict:
    """更换数据根目录：把当前目录整体复制到空目标，旧数据保留，重启后生效。"""
    new_root = validate_data_root((payload or {}).get("data_root", ""))
    old_root = os.path.normpath(DATA_ROOT)

    if new_root == old_root:
        raise HTTPException(
            status_code=400, detail=f"新目录与当前数据根目录相同：{old_root}"
        )

    # 新旧目录互为父子时复制会自嵌套，直接拒绝
    if old_root.startswith(new_root + os.sep) or new_root.startswith(old_root + os.sep):
        raise HTTPException(
            status_code=400,
            detail="新目录不能位于当前数据根目录内部，也不能是它的父目录",
        )

    # 目标必须是空目录（不存在则创建），避免与已有数据混在一起
    if os.path.exists(new_root):
        if not os.path.isdir(new_root):
            raise HTTPException(
                status_code=400, detail=f"目标路径不是文件夹：{new_root}"
            )
        if os.listdir(new_root):
            raise HTTPException(
                status_code=409,
                detail=f"目标文件夹必须为空：{new_root}（请清空后重试）",
            )
    else:
        try:
            os.makedirs(new_root, exist_ok=True)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"无法创建目标目录: {e}")

    # 整目录复制（agent_vm / embedding / memory 等全部带走），旧数据原样保留
    copied_files = 0
    if os.path.isdir(old_root):
        try:
            copied_files = sum(len(files) for _, _, files in os.walk(old_root))
            shutil.copytree(old_root, new_root, dirs_exist_ok=True)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"复制数据失败: {e}（目标目录不会被当作有效数据，清空后可重试）",
            )

    if not save_global_setting("data_root", new_root):
        raise HTTPException(
            status_code=500,
            detail="保存数据盘配置失败（数据已复制，修复权限后可重试）",
        )

    # 🌟 挂载路径已变化：销毁旧沙盒容器，重启后按新数据根自动重建，
    # 避免容器继续读写旧路径造成"沙盒写了、宿主看不到"的幽灵文件
    _destroy_sandbox_container()

    print(
        f"[Config API] 数据根目录已切换: {old_root} -> {new_root}"
        f"（复制 {copied_files} 个文件，旧数据保留，重启后生效）"
    )
    return {
        "status": "ok",
        "data_root": new_root,
        "old_data_root": old_root,
        "copied_files": copied_files,
        "message": "全部数据已复制到新位置（旧数据保留），沙盒容器已销毁，重启后生效",
    }


def _destroy_sandbox_container():
    """销毁旧沙盒容器（best-effort）：docker 不可用时忽略，由重启后的创建逻辑兜底。

    容器内的系统变更（apt 安装的包等）会随销毁丢失——这是预期行为：
    换根即换盘，旧挂载已无意义。
    """
    try:
        import docker
        from docker.errors import NotFound

        client = docker.from_env(timeout=5)
        container = client.containers.get("agent_computer")
        if container.status == "running":
            container.stop(timeout=2)
        container.remove(force=True)
        print("[Config API] 旧沙盒容器 (agent_computer) 已销毁，重启后按新数据根重建")
    except NotFound:
        pass  # 本来就没有容器
    except Exception as e:
        # docker 未装/引擎未启动：忽略，重启后 get_docker_manager 会按新 AGENT_VM_DIR 创建
        print(f"[Config API] 销毁旧沙盒容器失败(忽略，重启后重建): {e}")


# ── 部署与磁盘维护 ──
def deploy_overview() -> dict:
    """各依赖项就绪状态 + 部署任务进度与日志（前端轮询）"""
    from src.utils.deploy_manager import get_overview

    return get_overview()


def deploy_item(item: str) -> dict:
    """一键部署指定依赖项，后台线程执行，进度通过 GET /deploy 轮询"""
    from src.utils.deploy_manager import start_deploy

    ok, message = start_deploy(item)
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"status": "ok", "message": message}


def disk_status() -> dict:
    """只读取 Docker 数据盘占盘 / 有效数据估算 / 空洞占比（前端轮询，不阻塞不提权）"""
    from src.utils.disk_maintenance import get_disk_status

    return get_disk_status()


def compact_disk() -> dict:
    """一键回收 vhdx 空洞（后台线程，会短暂停止 Docker/WSL 并触发一次 UAC 授权）"""
    from src.utils.disk_maintenance import start_compact

    ok, message = start_compact()
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"status": "ok", "message": message}


def prune_disk() -> dict:
    """清理 Docker 构建缓存（后台线程，从源头降低 vhdx 增长速度）"""
    from src.utils.disk_maintenance import start_prune

    ok, message = start_prune()
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"status": "ok", "message": message}


def rebuild_sandbox() -> dict:
    """删除沙盒容器，下次工具调用自动重建（丢弃容器累积的可写层与缓存）"""
    from src.utils.disk_maintenance import rebuild_sandbox as _rebuild

    ok, message = _rebuild()
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"status": "ok", "message": message}


def get_sandbox_registry() -> dict:
    return {
        "sandbox_registry": str(get_global_settings().get("sandbox_registry") or "")
    }


def update_sandbox_registry(value: Any) -> dict:
    normalized = normalize_sandbox_registry(value)
    if not save_global_setting("sandbox_registry", normalized):
        raise HTTPException(status_code=500, detail="保存 sandbox_registry 失败")
    return {"status": "ok"}


# ── 沙盒目录挂载（SPEC-045） ──
def _inspect_sandbox_mounts() -> tuple[bool, bool, Dict[str, str]]:
    """(docker 可用, 容器存在, {容器路径: 宿主路径})，只读不启动容器。"""
    from src.utils import sandbox_mounts

    try:
        import docker
    except Exception:
        return False, False, {}
    try:
        client = docker.from_env(timeout=3)
        client.ping()
    except Exception:
        return False, False, {}
    try:
        container = client.containers.get("agent_computer")
        container.reload()
    except Exception:
        return True, False, {}

    actual: Dict[str, str] = {}
    try:
        for mount in container.attrs.get("Mounts") or []:
            destination = str(mount.get("Destination") or "")
            if destination.startswith(sandbox_mounts.CONTAINER_MOUNT_ROOT + "/"):
                actual[destination] = str(mount.get("Source") or "")
    except Exception:
        return True, True, {}
    return True, True, actual


def list_sandbox_mounts() -> dict:
    from src.tool.filesystem.utils import get_path_permission
    from src.utils import sandbox_mounts

    docker_ok, container_present, actual = _inspect_sandbox_mounts()
    items = []
    for item in sandbox_mounts.load_mounts():
        container_path = f"{sandbox_mounts.CONTAINER_MOUNT_ROOT}/{item['name']}"
        if not os.path.isdir(item["source"]):
            status = "missing"
        elif get_path_permission(item["source"]) == "blocked":
            status = "blocked"
        elif actual.get(container_path) and os.path.normcase(
            os.path.abspath(actual[container_path])
        ) == os.path.normcase(os.path.abspath(item["source"])):
            status = "active"
        else:
            status = "pending"
        items.append(
            {
                "name": item["name"],
                "source": item["source"],
                "container_path": container_path,
                "status": status,
            }
        )
    return {
        "docker_ok": docker_ok,
        "container_present": container_present,
        "mounts": items,
    }


def add_sandbox_mount(source: str, name: str | None = None) -> dict:
    from src.tool.filesystem.utils import get_path_permission
    from src.utils import sandbox_mounts

    mounts = sandbox_mounts.load_mounts()
    try:
        item = sandbox_mounts.validate_new_mount(source, name, mounts)
    except sandbox_mounts.MountError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if get_path_permission(item["source"]) == "blocked":
        raise HTTPException(status_code=400, detail="该目录被文件权限规则禁止访问")
    if not sandbox_mounts.save_mounts(mounts + [item]):
        raise HTTPException(status_code=500, detail="保存挂载配置失败")
    return {"status": "ok", "mount": item, **list_sandbox_mounts()}


def rename_sandbox_mount(name: str, new_name: str) -> dict:
    from src.utils import sandbox_mounts

    try:
        item = sandbox_mounts.rename_mount(name, new_name)
    except sandbox_mounts.MountError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "ok", "mount": item, **list_sandbox_mounts()}


def delete_sandbox_mount(name: str) -> dict:
    from src.utils import sandbox_mounts

    try:
        sandbox_mounts.remove_mount(name)
    except sandbox_mounts.MountError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"status": "ok", **list_sandbox_mounts()}


def apply_sandbox_mounts() -> dict:
    from src.tool.bash.docker_env import get_docker_manager

    try:
        get_docker_manager().apply_mounts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"应用挂载失败：{e}") from e
    return {"status": "ok", **list_sandbox_mounts()}

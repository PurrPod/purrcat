import os
import shutil
import time
import json
from src.tool.filesystem.exceptions import FileSystemError

HISTORY_DIR = os.path.join(os.getcwd(), ".agent_history")


def _get_history_path(target_path: str) -> str:
    """生成目标文件对应的历史备份路径 (终极防弹版)"""
    abs_path = os.path.abspath(target_path)
    norm_path = os.path.normcase(abs_path)
    safe_name = (
        norm_path.replace(os.sep, "%")
        .replace("/", "%")
        .replace("\\", "%")
        .replace(":", "")
    )
    return os.path.join(HISTORY_DIR, safe_name)


def track_edit(target_path: str) -> str:
    """在修改前备份文件，并返回唯一的时间戳 backup_id"""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    history_file = _get_history_path(target_path)

    backup_id = str(int(time.time() * 1000))
    backup_path = f"{history_file}@{backup_id}"

    if os.path.exists(target_path):
        shutil.copy2(target_path, backup_path)
    else:
        with open(backup_path + ".empty", "w") as f:
            f.write("")

    return backup_id


def save_backup_meta(target_path: str, backup_id: str, diff: str):
    """🌟 新增：保存包含 Diff 和元数据的 meta 文件"""
    history_file = _get_history_path(target_path)
    meta_path = f"{history_file}@{backup_id}.meta"
    
    # 获取简洁路径用于 UI 显示
    display_path = target_path
    if "agent_vm" in target_path:
        display_path = "/agent_vm" + target_path.split("agent_vm")[-1].replace("\\", "/")

    meta_data = {
        "id": f"diff_{backup_id}",
        "path": display_path,
        "backup_id": backup_id,
        "diff": diff,
        "time": time.strftime("%H:%M:%S", time.localtime(int(backup_id)/1000))
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, ensure_ascii=False)


def get_all_diffs() -> list:
    """🌟 新增：读取所有 meta 文件，返回全局 Diff 列表给前端"""
    if not os.path.exists(HISTORY_DIR):
        return []
    diffs = []
    for f in os.listdir(HISTORY_DIR):
        if f.endswith(".meta"):
            meta_path = os.path.join(HISTORY_DIR, f)
            try:
                with open(meta_path, "r", encoding="utf-8") as file:
                    diffs.append(json.load(file))
            except Exception:
                pass
    # 按时间戳倒序排列
    diffs.sort(key=lambda x: int(x["backup_id"]), reverse=True)
    return diffs


def ack_backup(target_path: str, backup_id: str):
    """用户确认更改，释放磁盘空间。执行【向前截断】：清理当前及更旧的备份"""
    if not backup_id:
        return
    history_file = _get_history_path(target_path)
    history_prefix = history_file + "@"

    for f in os.listdir(HISTORY_DIR):
        full_path = os.path.join(HISTORY_DIR, f)
        if full_path.startswith(history_prefix):
            try:
                # 🌟 重大修复：追加 .replace(".meta", "") 清理 meta 文件
                ts_str = f.replace(os.path.basename(history_prefix), "").replace(
                    ".empty", ""
                ).replace(".meta", "")
                # 核心：只要备份的时间戳 <= 当前确认的时间戳，就统统删掉！
                if ts_str and int(ts_str) <= int(backup_id):
                    os.remove(full_path)
            except ValueError:
                pass


def rewind_file_by_id(target_path: str, backup_id: str) -> str:
    """【重写】精确回滚，并解决非线性撤销导致的状态错乱"""
    if not backup_id:
        raise FileSystemError("精确回滚必须提供 backup_id。")

    history_file = _get_history_path(target_path)
    target_backup = f"{history_file}@{backup_id}"

    # 1. 执行物理恢复
    if os.path.exists(target_backup):
        shutil.copy2(target_backup, target_path)
        msg = "回滚成功：已精确穿越回该次修改前的状态。"
    elif os.path.exists(target_backup + ".empty"):
        if os.path.exists(target_path):
            os.remove(target_path)
        msg = "回滚成功：撤销了文件创建，已删除该文件。"
    else:
        raise FileSystemError(
            f"未找到版本号为 {backup_id} 的历史快照！它可能已被确认或销毁。"
        )

    # 2. 核心逻辑：时间线截断
    # 如果恢复了某个旧版本，那么比这个版本更"新"的备份在这个平行宇宙里就不存在了，必须全部销毁！
    history_prefix = history_file + "@"
    for f in os.listdir(HISTORY_DIR):
        full_path = os.path.join(HISTORY_DIR, f)
        if full_path.startswith(history_prefix):
            try:
                # 🌟 重大修复：追加 .replace(".meta", "") 清理 meta 文件
                ts_str = f.replace(os.path.basename(history_prefix), "").replace(
                    ".empty", ""
                ).replace(".meta", "")
                if ts_str and int(ts_str) >= int(backup_id):
                    os.remove(full_path)
            except ValueError:
                pass

    return msg


# 保留旧函数兼容性（可选）
def rewind_file(target_path: str) -> str:
    """回滚文件到上一个版本（兼容旧接口）"""
    if not os.path.exists(HISTORY_DIR):
        raise FileSystemError("没有找到历史记录目录。")

    history_prefix = _get_history_path(target_path) + "@"
    backups = []

    for f in os.listdir(HISTORY_DIR):
        full_path = os.path.join(HISTORY_DIR, f)
        if full_path.startswith(history_prefix):
            backups.append(full_path)

    if not backups:
        raise FileSystemError(f"未找到 {target_path} 的可回滚历史版本。")

    backups.sort(reverse=True)
    latest_backup = backups[0]

    # 提取 backup_id
    backup_id = os.path.basename(latest_backup).split("@")[-1].replace(".empty", "").replace(".meta", "")

    return rewind_file_by_id(target_path, backup_id)


def get_valid_backup_ids() -> list:
    """获取当前物理磁盘上真实存在的快照 ID 列表"""
    if not os.path.exists(HISTORY_DIR):
        return []

    valid_ids = set()
    for f in os.listdir(HISTORY_DIR):
        if "@" in f:
            # 提取文件名中 @ 后面的纯数字时间戳
            backup_id = f.split("@")[-1].replace(".empty", "").replace(".meta", "")
            if backup_id.isdigit():
                valid_ids.add(backup_id)

    return list(valid_ids)

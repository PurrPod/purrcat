import os
import mimetypes
import traceback
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.utils.path import convert_sandbox_path
from src.tool.filesystem.history import (
    rewind_file_by_id,
    ack_backup,
    get_valid_backup_ids,
    HISTORY_DIR,
    get_all_diffs,
)

router = APIRouter(prefix="/api/filesystem", tags=["UI Direct File Access"])


class UIRollbackReq(BaseModel):
    path: str
    backup_id: str


class UIWriteReq(BaseModel):
    path: str
    content: str


# ===== IDEPanel 文件操作（浏览器端降级用）=====
@router.get("/list")
def list_directory(path: str):
    """列出目录内容，返回 { name, isDir, path }[]"""
    try:
        entries = []
        for entry in sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith('.'):
                continue
            entries.append({
                'name': entry.name,
                'isDir': entry.is_dir(),
                'path': entry.path,
            })
        return entries
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/read")
def read_file(path: str):
    """读取文件文本内容（/agent_vm 沙盒路径自动转换，含 agent_vm 层缺失回退）"""
    try:
        resolved = _resolve_preview_path(path)
        with open(resolved, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return {'content': content}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stat")
def stat_file(path: str):
    """文件元信息（大小），IDE 大文件拦截用"""
    try:
        resolved = convert_sandbox_path(path)
        st = os.stat(resolved)
        return {'size': st.st_size}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/write")
def write_file(req: UIWriteReq):
    """写入文件文本内容（自动创建父目录，/agent_vm 沙盒路径自动转换）"""
    try:
        resolved = convert_sandbox_path(req.path)
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        with open(resolved, 'w', encoding='utf-8') as f:
            f.write(req.content)
        return {'status': 'success'}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/history_list")
def get_history_list():
    """直接读取 .agent_history 目录，返回真实存在的备份文件列表"""
    if not os.path.exists(HISTORY_DIR):
        return []

    files = os.listdir(HISTORY_DIR)
    history_list = []

    for f in files:
        if f.endswith(".empty"):
            continue

        # 解析文件名：safe_path@backup_id
        parts = f.rsplit("@", 1)
        if len(parts) != 2:
            continue

        safe_path_part = parts[0]
        backup_id = parts[1]

        # 还原原始路径格式
        original_path = safe_path_part.replace("%", os.sep)
        # 添加 / 前缀使其成为沙盒路径
        sandbox_path = "/" + original_path

        history_list.append(
            {
                "id": f,  # 使用完整文件名作为唯一ID
                "path": sandbox_path,
                "backup_id": backup_id,
                "time": "",  # 时间戳可自行转换
            }
        )

    return history_list


@router.get("/backups")
def api_get_valid_backups():
    """提供给前端：校验哪些快照还在硬盘上存活"""
    try:
        ids = get_valid_backup_ids()
        return {"status": "success", "valid_ids": ids}
    except Exception:
        traceback.print_exc()
        return {"status": "error", "valid_ids": []}


@router.post("/undo")
def ui_undo_action(req: UIRollbackReq):
    """提供给前端 UI 的一键回滚（最高权限）"""
    try:
        resolved_path = convert_sandbox_path(req.path)
        result_msg = rewind_file_by_id(resolved_path, req.backup_id)
        return {"status": "success", "message": result_msg}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"回滚失败: {str(e)}")


@router.post("/ack")
def ui_ack_action(req: UIRollbackReq):
    """用户确认更改，删除磁盘备份，解决空间膨胀"""
    try:
        resolved_path = convert_sandbox_path(req.path)
        ack_backup(resolved_path, req.backup_id)
        return {"status": "success"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"清理备份失败: {str(e)}")


@router.post("/ack_all")
def ui_ack_all_action():
    """一键接受全部更改：对所有未确认变更执行 ack，清理全部备份"""
    try:
        diffs = get_all_diffs()
        failed = 0
        for d in diffs:
            try:
                resolved_path = convert_sandbox_path(d["path"])
                ack_backup(resolved_path, d["newest_backup_id"])
            except Exception:
                traceback.print_exc()
                failed += 1
        if failed > 0:
            return {"status": "partial", "failed": failed, "total": len(diffs)}
        return {"status": "success", "total": len(diffs)}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"批量清理备份失败: {str(e)}")


@router.get("/diffs")
def api_get_global_diffs():
    """🌟 新增：提供给前端全局读取所有未确认的代码变更 (DiffView)"""
    try:
        diffs = get_all_diffs()
        return {"status": "success", "diffs": diffs}
    except Exception as e:
        import traceback

        traceback.print_exc()
        # 🌟 修改这里：把报错的详细信息放到返回体里
        return {"status": "error", "diffs": [], "message": str(e)}


def _resolve_preview_path(path: str) -> str:
    """
    将前端传来的（可能是沙盒或相对）路径映射为真实物理绝对路径。
    含 agent_vm 沙盒层缺失时的回退查找逻辑。
    """
    resolved_path = convert_sandbox_path(path)

    # 路径回退：Agent 有时输出的路径漏掉了 agent_vm 沙盒层
    # 如果原始路径找不到，且路径不含 agent_vm，尝试在 agent_vm 下查找
    if not os.path.exists(resolved_path) or not os.path.isfile(resolved_path):
        norm = path.replace("\\", "/")
        if "agent_vm" not in norm:
            # 尝试拼上 agent_vm 前缀再找一次
            # 去掉可能的盘符前缀 (D:/xxx -> xxx) 再拼 agent_vm
            stripped = norm
            if len(stripped) >= 2 and stripped[1] == ":":
                stripped = stripped[2:]
            stripped = stripped.lstrip("/")
            fallback = convert_sandbox_path(f"/agent_vm/{stripped}")
            if os.path.exists(fallback) and os.path.isfile(fallback):
                resolved_path = fallback

    return resolved_path


@router.get("/resolve")
def resolve_path(path: str):
    """
    返回沙盒/相对路径对应的宿主机真实绝对路径。
    供前端构造 file:// URL，在内置浏览器中打开本地 HTML/SVG
    （复用内置浏览器的元素 pick + 评论能力）。
    """
    try:
        resolved = _resolve_preview_path(path)
        if not os.path.isfile(resolved):
            raise HTTPException(status_code=404, detail=f"File not found: {path}")
        return {"real_path": resolved}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/preview")
def preview_file(path: str):
    """
    接收绝对路径，返回文件流给前端预览。
    用于绕过浏览器对 file:// 协议的同源与安全限制。
    """
    resolved_path = _resolve_preview_path(path)

    if not os.path.exists(resolved_path) or not os.path.isfile(resolved_path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    mime_type, _ = mimetypes.guess_type(resolved_path)
    if not mime_type:
        mime_type = "application/octet-stream"

    return FileResponse(resolved_path, media_type=mime_type)

import traceback
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.agent.project_store import ProjectStore

router = APIRouter(prefix="/api", tags=["Projects"])


class ProjectCreateReq(BaseModel):
    name: str


class ProjectUpdateReq(BaseModel):
    name: Optional[str] = None


def _session_counts():
    from src.agent.session_store import SessionStore

    counts = {}
    for info in SessionStore.get_all_sessions().values():
        project_id = (info or {}).get("project_id")
        if project_id:
            counts[project_id] = counts.get(project_id, 0) + 1
    return counts


@router.get("/projects")
def list_projects_api():
    """列出全部项目（按创建时间升序），附带各自的会话数量。"""
    try:
        counts = _session_counts()
        projects = ProjectStore.list_projects()
        for project in projects:
            project["session_count"] = counts.get(project["id"], 0)
            # 记忆文件由 Agent 自行维护，前端只展示它的位置
            project["memory_path"] = ProjectStore.memory_path(project["id"])
        return projects
    except Exception as e:
        print(f"[ERROR] /api/projects - 异常: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/projects")
def create_project_api(req: ProjectCreateReq):
    """新建项目：创建项目文件夹与 MEMORY.md（仅写入自身位置），并写入索引。"""
    try:
        project = ProjectStore.create_project(req.name)
        project["session_count"] = 0
        return project
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        print(f"[ERROR] /api/projects - 异常: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/projects/{project_id}")
def update_project_api(project_id: str, req: ProjectUpdateReq):
    """更新项目名称。"""
    if not ProjectStore.get_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    try:
        project = ProjectStore.update_project(project_id, name=req.name)
        project["session_count"] = _session_counts().get(project_id, 0)
        project["memory_path"] = ProjectStore.memory_path(project_id)
        return project
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        print(f"[ERROR] /api/projects/{project_id} - 异常: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/projects/{project_id}")
def delete_project_api(project_id: str, delete_sessions: bool = False):
    """删除项目。

    - delete_sessions=false：会话保留，仅解除项目归属（回到「未分类」）。
    - delete_sessions=true：连同项目内会话一起删除；若含当前活跃会话则拒绝（400）。
    """
    from src.agent.manager import AgentManager
    from src.agent.session_store import SessionStore

    if not ProjectStore.get_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")

    session_ids = [
        sid
        for sid, info in SessionStore.get_all_sessions().items()
        if (info or {}).get("project_id") == project_id
    ]

    if not delete_sessions:
        for sid in session_ids:
            SessionStore.set_session_project(sid, None)
        ProjectStore.delete_project(project_id)
        return {"status": "ok", "deleted_sessions": 0}

    manager = AgentManager()
    active = manager.get_active_session_id()
    if active in session_ids:
        raise HTTPException(
            status_code=400, detail="当前活跃会话属于该项目，请先切换到其它会话再删除"
        )

    deleted, failed = 0, 0
    for sid in session_ids:
        try:
            manager.delete_session(sid)
            deleted += 1
        except Exception as e:
            failed += 1
            print(f"[ERROR] 删除项目内会话 {sid} 失败: {e}")
    if failed:
        raise HTTPException(
            status_code=500,
            detail=f"已删除 {deleted} 个会话，{failed} 个失败；项目保留，可重试",
        )

    ProjectStore.delete_project(project_id)
    return {"status": "ok", "deleted_sessions": deleted}

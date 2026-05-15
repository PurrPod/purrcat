from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from src.agent.manager import manager
from src.utils.session_api import list_sessions, get_session_history, create_session, delete_session, run_agent_task

router = APIRouter(prefix="/api", tags=["Chat & Sessions"])

class NewSessionReq(BaseModel):
    alias: str = "New Session"

class ChatReq(BaseModel):
    session_id: str
    message: str

@router.get("/sessions")
def get_sessions():
    sessions_dict = list_sessions()
    sess_list = []
    for sid, info in sessions_dict.items():
        sess_list.append({
            "id": sid,
            "alias": info.get("alias", sid),
            "messages_count": info.get("messages_count", 0),
            "updated_at": info.get("updated_at", "")
        })
    sess_list.sort(key=lambda x: x["updated_at"], reverse=True)
    return sess_list

@router.get("/sessions/{session_id}")
def get_session_history_api(session_id: str):
    return get_session_history(session_id)

@router.post("/sessions/new")
def create_new_session(req: NewSessionReq):
    return create_session(req.alias)

@router.delete("/sessions/{session_id}")
def delete_session_api(session_id: str):
    return delete_session(session_id)

@router.post("/chat")
def chat(req: ChatReq, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_agent_task, req.session_id, req.message)
    return {"status": "processing", "message": "Message pushed to agent"}


@router.get("/sessions/{session_id}/status")
def get_session_status(session_id: str):
    """
    轻量级轮询接口：检查当前会话的后台 Agent 是否还在活跃运行
    """
    try:
        # 获取全局唯一 Agent 实例
        agent = manager._agent
        
        # 确保 Agent 存在，并且当前正在处理的就是我们请求的这个 session_id
        if agent and agent.session_id == session_id:
            # 在 agent.py 中，空闲时 state 为 "idle"，工作时为 "handling"
            is_thinking = agent.state != "idle"
            return {
                "is_thinking": is_thinking,
                "state": agent.state
            }
        
        return {"is_thinking": False, "state": "idle"}
    except Exception as e:
        print(f"获取Agent状态失败: {e}")
        return {"is_thinking": False, "state": "idle"}

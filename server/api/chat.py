import os
import json
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

# 引入项目核心组件
from src.agent.session_store import SessionStore
from src.agent.manager import manager
from src.utils.config import DATA_DIR

router = APIRouter(prefix="/api", tags=["Chat & Sessions"])

class NewSessionReq(BaseModel):
    alias: str = "New Session"

class ChatReq(BaseModel):
    session_id: str
    message: str

@router.get("/sessions")
def get_sessions():
    sessions_dict = manager.list_sessions()
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
def get_session_history(session_id: str):
    current_agent = manager.get_agent()
    if current_agent and current_agent.session_id == session_id:
        history = current_agent.get_history()
    else:
        history = SessionStore.load_session_history(session_id)
    return [m for m in history if m.get("role") != "system"]

@router.post("/sessions/new")
def create_new_session(req: NewSessionReq):
    new_id = manager.create_clean_session(req.alias)
    return {"id": new_id, "alias": req.alias}

# 🔴 新增：删除会话功能
@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    # 1. 删除磁盘 session JSON 文件
    session_file = os.path.join(DATA_DIR, "checkpoints", "agent", f"session_{session_id}.json")
    if os.path.exists(session_file):
        os.remove(session_file)
    
    # 2. 从 index.json 注册表中抹除记录
    index_file = os.path.join(DATA_DIR, "checkpoints", "agent", "index.json")
    if os.path.exists(index_file):
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                idx = json.load(f)
            if session_id in idx:
                del idx[session_id]
                with open(index_file, "w", encoding="utf-8") as f:
                    json.dump(idx, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error updating index: {e}")

    # 3. 如果恰好删除了正在挂载的会话，强制其创建并检出一个新纯净会话
    current_agent = manager.get_agent()
    if current_agent and current_agent.session_id == session_id:
        manager.create_clean_session("New Session")
        
    return {"status": "ok", "message": "Session deleted"}

def run_agent_task(session_id: str, message: str):
    if manager.get_agent().session_id != session_id:
        manager.checkout_session(session_id)
    agent = manager.get_agent()
    agent.force_push(message, type="user")

@router.post("/chat")
def chat(req: ChatReq, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_agent_task, req.session_id, req.message)
    return {"status": "processing", "message": "Message pushed to agent"}
import os
import json
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from src.agent.session_store import SessionStore
from src.agent.manager import manager
from src.utils.config import DATA_DIR
from src.utils.session_api import list_sessions, get_session_history, create_session, delete_session, run_agent_task

router = APIRouter(prefix="/api", tags=["Chat & Sessions"])

class NewSessionReq(BaseModel):
    alias: str = "New Session"

class ChatReq(BaseModel):
    session_id: str
    message: str

@router.get("/sessions")
def get_sessions():
    return list_sessions()

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

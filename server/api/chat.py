import traceback

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from src.agent.manager import manager
from src.utils.session_api import (
    create_session,
    delete_session,
    ensure_manager_initialized,
    get_session_history,
    list_sessions,
    run_agent_task,
)

router = APIRouter(prefix="/api", tags=["Chat & Sessions"])


class NewSessionReq(BaseModel):
    alias: str = "New Session"


class ChatReq(BaseModel):
    session_id: str
    message: str


@router.get("/sessions")
def get_sessions():
    print("[DEBUG] /api/sessions - 开始获取会话列表")
    try:
        ensure_manager_initialized()
        sessions_dict = list_sessions()
        sess_list = []
        for sid, info in sessions_dict.items():
            sess_list.append(
                {
                    "id": sid,
                    "alias": info.get("alias", sid),
                    "messages_count": info.get("messages_count", 0),
                    "updated_at": info.get("updated_at", ""),
                }
            )
        sess_list.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
        print(f"[DEBUG] /api/sessions - 获取到 {len(sess_list)} 个会话")
        return sess_list
    except Exception as e:
        print(f"[ERROR] /api/sessions - 异常: {e}")
        traceback.print_exc()
        raise


@router.post("/sessions/{session_id}/checkout")
def checkout_session_api(session_id: str):
    print(f"[DEBUG] /api/sessions/{session_id}/checkout - 开始检出会话")
    try:
        from src.utils.session_api import checkout_session

        ensure_manager_initialized()
        success = checkout_session(session_id)
        print(f"[DEBUG] /api/sessions/{session_id}/checkout - 完成，成功: {success}")
        return {"status": "ok" if success else "error"}
    except Exception as e:
        print(f"[ERROR] /api/sessions/{session_id}/checkout - 异常: {e}")
        traceback.print_exc()
        raise


@router.get("/sessions/{session_id}")
def get_session_history_api(session_id: str):
    print(f"[DEBUG] /api/sessions/{session_id} - 开始获取会话历史")
    try:
        ensure_manager_initialized()
        history = get_session_history(session_id)
        print(f"[DEBUG] /api/sessions/{session_id} - 获取到 {len(history)} 条历史消息")
        return history
    except Exception as e:
        print(f"[ERROR] /api/sessions/{session_id} - 异常: {e}")
        traceback.print_exc()
        raise


@router.post("/sessions/new")
def create_new_session(req: NewSessionReq):
    print(f"[DEBUG] /api/sessions/new - 开始创建会话，别名: {req.alias}")
    try:
        ensure_manager_initialized()
        result = create_session(req.alias)
        print(f"[DEBUG] /api/sessions/new - 会话创建成功: {result}")
        return result
    except Exception as e:
        print(f"[ERROR] /api/sessions/new - 异常: {e}")
        traceback.print_exc()
        raise


@router.delete("/sessions/{session_id}")
def delete_session_api(session_id: str):
    print(f"[DEBUG] /api/sessions/{session_id} - 开始删除会话")
    try:
        ensure_manager_initialized()
        result = delete_session(session_id)
        print(f"[DEBUG] /api/sessions/{session_id} - 删除完成: {result}")
        return result
    except Exception as e:
        print(f"[ERROR] /api/sessions/{session_id} - 异常: {e}")
        traceback.print_exc()
        raise


@router.post("/chat")
def chat(req: ChatReq, background_tasks: BackgroundTasks):
    print(f"[DEBUG] /api/chat - 收到消息，session_id: {req.session_id}")
    try:
        ensure_manager_initialized()
        background_tasks.add_task(run_agent_task, req.session_id, req.message)
        print("[DEBUG] /api/chat - 消息已加入后台任务")
        return {"status": "processing", "message": "Message pushed to agent"}
    except Exception as e:
        print(f"[ERROR] /api/chat - 异常: {e}")
        traceback.print_exc()
        raise


@router.get("/sessions/{session_id}/status")
def get_session_status(session_id: str):
    """
    轻量级轮询接口：检查当前会话的后台 Agent 是否还在活跃运行
    """
    try:
        ensure_manager_initialized()
        # 获取全局唯一 Agent 实例
        agent = manager._agent

        # 确保 Agent 存在，并且当前正在处理的就是我们请求的这个 session_id
        if agent and agent.session_id == session_id:
            # 在 agent.py 中，空闲时 state 为 "idle"，工作时为 "handling"
            is_thinking = agent.state != "idle"
            result = {"is_thinking": is_thinking, "state": agent.state}
        else:
            result = {"is_thinking": False, "state": "idle"}

        print(f"[DEBUG] /api/sessions/{session_id}/status - 返回: {result}")
        return result
    except Exception as e:
        print(f"[ERROR] /api/sessions/{session_id}/status - 异常: {e}")
        traceback.print_exc()
        return {"is_thinking": False, "state": "idle"}

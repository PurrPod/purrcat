import traceback

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from src.agent import (
    delete_session,
    get_agent_status,
    get_chat_history,
    get_session_list,
    init_agent,
    new_session,
)

router = APIRouter(prefix="/api", tags=["Chat & Sessions"])


class NewSessionReq(BaseModel):
    alias: str = "New Session"


class BranchSessionReq(BaseModel):
    alias: str = "Branch Session"


class ChatReq(BaseModel):
    session_id: str
    message: str


def _ensure_manager_initialized():
    init_agent()


def _run_agent_task(session_id: str, message: str):
    from src.agent.manager import AgentManager
    import time

    manager = AgentManager()
    if manager._agent is None:
        manager.init_agent()

    if manager._agent.session_id != session_id:
        if manager._agent.state != "idle":
            while manager._agent.state != "idle":
                time.sleep(0.3)
        manager.switch_session(session_id)

    manager.agent_force_push(message, type="user")


@router.get("/sessions")
def get_sessions():
    print("[DEBUG] /api/sessions - 开始获取会话列表")
    try:
        _ensure_manager_initialized()
        sessions_dict = get_session_list()
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
        from src.agent import switch_session

        _ensure_manager_initialized()
        switch_session(session_id)
        print(f"[DEBUG] /api/sessions/{session_id}/checkout - 完成")
        return {"status": "ok"}
    except Exception as e:
        print(f"[ERROR] /api/sessions/{session_id}/checkout - 异常: {e}")
        traceback.print_exc()
        raise


@router.get("/sessions/{session_id}")
def get_session_history_api(session_id: str):
    print(f"[DEBUG] /api/sessions/{session_id} - 开始获取会话历史")
    try:
        _ensure_manager_initialized()
        history = get_chat_history(session_id)
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
        _ensure_manager_initialized()
        session_id = new_session(branch_alias=req.alias)
        print(f"[DEBUG] /api/sessions/new - 会话创建成功: {session_id}")
        return {"id": session_id, "alias": req.alias or session_id}
    except Exception as e:
        print(f"[ERROR] /api/sessions/new - 异常: {e}")
        traceback.print_exc()
        raise


@router.post("/sessions/{session_id}/branch")
def branch_session_api(session_id: str, req: BranchSessionReq):
    print(
        f"[DEBUG] /api/sessions/{session_id}/branch - 开始衍生新分支，别名: {req.alias}"
    )
    try:
        from src.agent import switch_session, branch_session

        _ensure_manager_initialized()

        switch_session(session_id)

        new_id = branch_session(branch_alias=req.alias)

        print(f"[DEBUG] /api/sessions/{session_id}/branch - 分支创建成功: {new_id}")
        return {"id": new_id, "alias": req.alias}
    except Exception as e:
        print(f"[ERROR] /api/sessions/{session_id}/branch - 异常: {e}")
        traceback.print_exc()
        raise


@router.delete("/sessions/{session_id}")
def delete_session_api(session_id: str):
    print(f"[DEBUG] /api/sessions/{session_id} - 开始删除会话")
    try:
        _ensure_manager_initialized()
        delete_session(session_id)
        print(f"[DEBUG] /api/sessions/{session_id} - 删除完成")
        return {"status": "ok"}
    except Exception as e:
        print(f"[ERROR] /api/sessions/{session_id} - 异常: {e}")
        traceback.print_exc()
        raise


@router.post("/chat")
def chat(req: ChatReq, background_tasks: BackgroundTasks):
    print(f"[DEBUG] /api/chat - 收到消息，session_id: {req.session_id}")
    try:
        _ensure_manager_initialized()
        background_tasks.add_task(_run_agent_task, req.session_id, req.message)
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
        _ensure_manager_initialized()
        status = get_agent_status()

        if status.get("session_id") == session_id:
            is_thinking = status.get("state") != "idle"
            result = {"is_thinking": is_thinking, "state": status.get("state", "idle")}
        else:
            result = {"is_thinking": False, "state": "idle"}

        print(f"[DEBUG] /api/sessions/{session_id}/status - 返回: {result}")
        return result
    except Exception as e:
        print(f"[ERROR] /api/sessions/{session_id}/status - 异常: {e}")
        traceback.print_exc()
        return {"is_thinking": False, "state": "idle"}

import traceback

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from src.agent import (
    delete_session,
    get_agent_status,
    get_chat_history,
    get_session_list,
    init_agent,
    new_session,
    get_window_token,
    get_agent_max_token,
    agent_force_interrupt,
    flush_agent_memory,
)

router = APIRouter(prefix="/api", tags=["Chat & Sessions"])


class NewSessionReq(BaseModel):
    alias: str = "New Session"


# 👇 新增：重命名模型
class RenameSessionReq(BaseModel):
    alias: str


class BranchSessionReq(BaseModel):
    alias: str = "Branch Session"


class ChatReq(BaseModel):
    session_id: str
    message: str


class ChatBatchReq(BaseModel):
    session_id: str
    events: list


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


def _run_agent_batch_task(session_id: str, events: list):
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

    manager.agent_force_push_batch(events)


@router.get("/sessions")
def get_sessions():
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
        return sess_list
    except Exception as e:
        print(f"[ERROR] /api/sessions - 异常: {e}")
        traceback.print_exc()
        raise


# 👇 新增：重命名 API 接口
@router.put("/sessions/{session_id}/rename")
def rename_session_api(session_id: str, req: RenameSessionReq):
    try:
        import os
        import json
        from src.agent.session_store import SessionStore
        from src.utils.config import SESSIONS_DIR, SESSION_INDEX_PATH

        # 1. 更新索引
        with SessionStore._index_lock:
            index_data = SessionStore.get_all_sessions()
            if session_id in index_data:
                index_data[session_id]["alias"] = req.alias
                with open(SESSION_INDEX_PATH, "w", encoding="utf-8") as f:
                    json.dump(index_data, f, ensure_ascii=False, indent=2)

        # 2. 更新元数据
        meta_path = os.path.join(SESSIONS_DIR, session_id, "meta.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
            meta_data["alias"] = req.alias
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)

        return {"status": "ok"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# 👇 修改 checkout 接口，物理阻断恶意 session_id (如 requests) 的污染
@router.post("/sessions/{session_id}/checkout")
def checkout_session_api(session_id: str):
    if not session_id.startswith("session_"):
        raise HTTPException(status_code=400, detail="Invalid session ID")
    try:
        from src.agent import switch_session

        _ensure_manager_initialized()
        switch_session(session_id)
        return {"status": "ok"}
    except Exception as e:
        print(f"[ERROR] /api/sessions/{session_id}/checkout - 异常: {e}")
        traceback.print_exc()
        raise


@router.get("/sessions/{session_id}")
def get_session_history_api(session_id: str, branch_id: str = "main"):
    try:
        _ensure_manager_initialized()
        # 🌟 传入 branch_id 支持子分支读取
        history = get_chat_history(session_id, branch_id=branch_id)
        return history
    except Exception as e:
        print(f"[ERROR] /api/sessions/{session_id} - 异常: {e}")
        traceback.print_exc()
        raise


@router.get("/sessions/{session_id}/branches")
def get_session_branches_api(session_id: str):
    """🌟 新增：获取当前会话下所有活跃或已完成的子分支元数据"""
    try:
        import os
        import json
        from src.utils.config import SESSIONS_DIR

        meta_path = os.path.join(SESSIONS_DIR, session_id, "meta.json")
        if not os.path.exists(meta_path):
            return {"main": {"status": "active"}}
        with open(meta_path, "r", encoding="utf-8") as f:
            meta_data = json.load(f)
        return meta_data.get("branches", {"main": {"status": "active"}})
    except Exception:
        return {"main": {"status": "active"}}


@router.post("/sessions/new")
def create_new_session(req: NewSessionReq):
    try:
        _ensure_manager_initialized()
        session_id = new_session(branch_alias=req.alias)
        return {"id": session_id, "alias": req.alias or session_id}
    except Exception as e:
        print(f"[ERROR] /api/sessions/new - 异常: {e}")
        traceback.print_exc()
        raise


@router.post("/sessions/{session_id}/branch")
def branch_session_api(session_id: str, req: BranchSessionReq):

    try:
        from src.agent import switch_session, branch_session

        _ensure_manager_initialized()

        switch_session(session_id)

        new_id = branch_session(branch_alias=req.alias)

        return {"id": new_id, "alias": req.alias}
    except Exception as e:
        print(f"[ERROR] /api/sessions/{session_id}/branch - 异常: {e}")
        traceback.print_exc()
        raise


@router.delete("/sessions/{session_id}")
def delete_session_api(session_id: str):
    try:
        _ensure_manager_initialized()
        delete_session(session_id)
        return {"status": "ok"}
    except Exception as e:
        print(f"[ERROR] /api/sessions/{session_id} - 异常: {e}")
        traceback.print_exc()
        raise


@router.post("/chat")
def chat(req: ChatReq, background_tasks: BackgroundTasks):
    try:
        _ensure_manager_initialized()
        background_tasks.add_task(_run_agent_task, req.session_id, req.message)
        return {"status": "processing", "message": "Message pushed to agent"}
    except Exception as e:
        print(f"[ERROR] /api/chat - 异常: {e}")
        traceback.print_exc()
        raise


@router.post("/chat/batch")
def chat_batch(req: ChatBatchReq, background_tasks: BackgroundTasks):
    try:
        _ensure_manager_initialized()

        # 🌟 预处理：字数检验替换（与 Agent.force_push_batch 保持一致）
        from src.agent.agent import Agent

        processed_events = []
        for event in req.events:
            event_type = event.get("type", "user")
            event_content = event.get("content", "")
            event_content = Agent._buffer_long_user_input(event_content, event_type)
            processed_events.append({**event, "content": event_content})

        # 后台仍走原流程，传入原始 events（force_push_batch 内部也会做字数检验）
        background_tasks.add_task(_run_agent_batch_task, req.session_id, req.events)

        return {"status": "processing", "processed_events": processed_events}
    except Exception as e:
        print(f"[ERROR] /api/chat/batch - 异常: {e}")
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
            result = {"is_thinking": is_thinking, "state": status.get("state", "idle"), "compressing": status.get("compressing", False)}
        else:
            result = {"is_thinking": False, "state": "idle", "compressing": status.get("compressing", False)}
        return result
    except Exception as e:
        print(f"[ERROR] /api/sessions/{session_id}/status - 异常: {e}")
        traceback.print_exc()
        return {"is_thinking": False, "state": "idle"}


@router.post("/chat/interrupt")
def force_interrupt_api():
    """
    🌟 人类强制打断：物理掐断 Agent 正在执行的工具（子进程 terminate），
    隔离旧响应并注入打断提示，Agent 立即回到 idle 状态
    """
    try:
        _ensure_manager_initialized()
        ok = agent_force_interrupt()
        return {"status": "ok" if ok else "no_agent", "interrupted": ok}
    except Exception as e:
        print(f"[ERROR] /api/chat/interrupt - 异常: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/compress-memory")
def compress_memory_api(background_tasks: BackgroundTasks):
    """
    🌟 手动触发 Agent 记忆压缩：全局大总结并截断历史上下文
    （内部需调用 LLM 生成摘要，耗时较长，放后台任务避免 HTTP 超时）
    """
    try:
        _ensure_manager_initialized()
        background_tasks.add_task(_run_memory_compression)
        return {"status": "processing"}
    except Exception as e:
        print(f"[ERROR] /api/chat/compress-memory - 异常: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _run_memory_compression():
    try:
        ok = flush_agent_memory()
        print(f"[Memory] 手动记忆压缩完成: {'成功' if ok else '失败(无Agent实例)'}")
    except Exception as e:
        print(f"[ERROR] 记忆压缩后台任务异常: {e}")
        traceback.print_exc()


@router.get("/agent/token")
def get_token_status_api():
    """获取当前 Agent 的上下文 Token 使用进度"""
    try:
        _ensure_manager_initialized()
        return {"window_token": get_window_token(), "max_token": get_agent_max_token()}
    except Exception:
        import traceback

        traceback.print_exc()
        return {"window_token": 0, "max_token": 1000000}


@router.delete("/sessions/{session_id}/branches/{branch_id}")
def delete_session_branch_api(session_id: str, branch_id: str):
    try:
        from src.agent.sub_runner import cancel_sub_branch

        # 🌟 修复：删除分支前，如果该分支在后台跑，直接一刀斩断！
        cancel_sub_branch(branch_id)

        from src.agent.session_store import SessionStore

        success = SessionStore.delete_branch(session_id, branch_id)
        if success:
            return {"status": "ok"}
        raise HTTPException(status_code=400, detail="分支不存在或禁止删除主干分支")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

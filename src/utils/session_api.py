import json
import os

from src.agent.manager import manager
from src.agent.session_store import SessionStore
from src.utils.config import DATA_DIR


def ensure_manager_initialized():
    """确保 manager 被正确初始化"""
    if getattr(manager, "_agent", None) is None:
        manager.init_agent()


def list_sessions():
    ensure_manager_initialized()
    return manager.list_sessions()


def get_session_history(session_id: str):
    ensure_manager_initialized()
    current_agent = getattr(manager, "_agent", None)
    if current_agent and current_agent.session_id == session_id:
        history = current_agent.get_history()
    else:
        history = SessionStore.load_session_history(session_id)
    return [m for m in history if m.get("role") != "system"]


def create_session(alias: str = "New Session"):
    ensure_manager_initialized()
    new_id = manager.create_clean_session(alias)
    return {"id": new_id, "alias": alias}


def delete_session(session_id: str):
    """删除会话，使用 SessionStore 的正确实现"""
    ensure_manager_initialized()

    session_file = os.path.join(DATA_DIR, "checkpoints", "agent", f"{session_id}.json")
    if os.path.exists(session_file):
        os.remove(session_file)

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

    return {"status": "ok", "message": "Session deleted"}


def run_agent_task(session_id: str, message: str):
    ensure_manager_initialized()
    if manager.get_agent().session_id != session_id:
        manager.checkout_session(session_id)
    agent = manager.get_agent()
    agent.force_push(message, type="user")


def get_current_session_id():
    ensure_manager_initialized()
    try:
        return manager.get_agent().session_id
    except Exception:
        return None


def branch_session(branch_alias=None):
    ensure_manager_initialized()
    return manager.branch_current_session(branch_alias)


def checkout_session(target_session_id: str):
    ensure_manager_initialized()
    agent = getattr(manager, "_agent", None)
    if not agent:
        manager.init_agent(session_id=target_session_id)
        return True
    return manager.checkout_session(target_session_id)


def new_clean_session(branch_alias=None):
    ensure_manager_initialized()
    return manager.create_clean_session(branch_alias)

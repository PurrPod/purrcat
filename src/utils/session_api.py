import os
import json
from src.agent.session_store import SessionStore
from src.agent.manager import manager
from src.utils.config import DATA_DIR, SESSIONS_DIR


def list_sessions():
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


def get_session_history(session_id: str):
    current_agent = manager.get_agent()
    if current_agent and current_agent.session_id == session_id:
        history = current_agent.get_history()
    else:
        history = SessionStore.load_session_history(session_id)
    return [m for m in history if m.get("role") != "system"]


def create_session(alias: str = "New Session"):
    new_id = manager.create_clean_session(alias)
    return {"id": new_id, "alias": alias}


def delete_session(session_id: str):
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
    if manager.get_agent().session_id != session_id:
        manager.checkout_session(session_id)
    agent = manager.get_agent()
    agent.force_push(message, type="user")


def get_current_session_id():
    try:
        return manager.get_agent().session_id
    except Exception:
        return None


def branch_session(branch_alias=None):
    return manager.branch_current_session(branch_alias)


def checkout_session(target_session_id: str):
    return manager.checkout_session(target_session_id)


def new_clean_session(branch_alias=None):
    return manager.create_clean_session(branch_alias)

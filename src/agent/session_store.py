import os
import json
import uuid
import time
import threading
from src.utils.config import SESSIONS_DIR, SESSION_INDEX_PATH


class SessionStore:
    _index_lock = threading.RLock()
    _file_locks = {}  # 用于存储每个session文件的锁: {session_id: threading.Lock()}
    _file_locks_lock = threading.Lock()  # 保护 _file_locks 字典本身

    @classmethod
    def _get_file_lock(cls, session_id):
        """获取指定session_id的文件锁，线程安全"""
        with cls._file_locks_lock:
            if session_id not in cls._file_locks:
                cls._file_locks[session_id] = threading.Lock()
            return cls._file_locks[session_id]

    @staticmethod
    def _generate_id():
        return f"session_{uuid.uuid4().hex[:8]}"

    @classmethod
    def get_all_sessions(cls):
        with cls._index_lock:
            if os.path.exists(SESSION_INDEX_PATH):
                try:
                    with open(SESSION_INDEX_PATH, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
            return {}

    @classmethod
    def load_session_history(cls, session_id):
        path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if not os.path.exists(path): return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ 读取会话 {session_id} 失败: {e}")
            return []

    @classmethod
    def save_session(cls, session_id, history, parent_id=None, alias=None):
        path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        temp_path = f"{path}.tmp"
        
        # 获取该session的文件锁，防止并发写入
        file_lock = cls._get_file_lock(session_id)
        with file_lock:
            try:
                # 临时文件写入保障断电不丢数据
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                os.replace(temp_path, path)
            except Exception as e:
                print(f"⚠️ 保存会话内容失败: {e}")
                return

        with cls._index_lock:
            index_data = cls.get_all_sessions()
            session_info = index_data.get(session_id, {})
            if not session_info:
                session_info = {
                    "created_at": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "parent_id": parent_id,
                    "alias": alias or session_id,
                }
            session_info["updated_at"] = time.strftime('%Y-%m-%d %H:%M:%S')
            session_info["messages_count"] = len(history)
            index_data[session_id] = session_info

            try:
                with open(SESSION_INDEX_PATH, "w", encoding="utf-8") as f:
                    json.dump(index_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"⚠️ 保存会话索引失败: {e}")

    @classmethod
    def create_branch(cls, current_session_id, current_history, branch_alias=None):
        new_session_id = cls._generate_id()
        # 由于传入的 current_history 已经是深拷贝副本，无需在此重复深拷贝
        cls.save_session(
            session_id=new_session_id,
            history=current_history,
            parent_id=current_session_id,
            alias=branch_alias
        )
        return new_session_id
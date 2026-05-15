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
    def load_global_memo(cls):
        """读取全局共享的缓存记忆列表"""
        path = os.path.join(SESSIONS_DIR, "memo.json")
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ 读取全局 memo 失败: {e}")
            return []

    @classmethod
    def save_global_memo(cls, memo_list):
        """持久化存储全局共享的缓存记忆列表"""
        path = os.path.join(SESSIONS_DIR, "memo.json")
        temp_path = f"{path}.tmp"
        with cls._index_lock:
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(memo_list, f, ensure_ascii=False, indent=2)
                os.replace(temp_path, path)
            except Exception as e:
                print(f"⚠️ 保存全局 memo 失败: {e}")

    @classmethod
    def get_all_sessions(cls):
        with cls._index_lock:
            index_data = {}
            if os.path.exists(SESSION_INDEX_PATH):
                try:
                    with open(SESSION_INDEX_PATH, "r", encoding="utf-8") as f:
                        index_data = json.load(f)
                except Exception:
                    pass

            sessions_to_remove = []
            for session_id in index_data:
                session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
                if not os.path.exists(session_file):
                    sessions_to_remove.append(session_id)
            for session_id in sessions_to_remove:
                del index_data[session_id]

            if os.path.exists(SESSIONS_DIR):
                for filename in os.listdir(SESSIONS_DIR):
                    if filename.endswith(".json") and filename not in ["index.json", "memo.json"]:
                        session_id = filename[:-5]

                        if session_id not in index_data:
                            file_path = os.path.join(SESSIONS_DIR, filename)
                            try:
                                file_stat = os.stat(file_path)
                                created_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_stat.st_ctime))
                                updated_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_stat.st_mtime))

                                with open(file_path, "r", encoding="utf-8") as f:
                                    history = json.load(f)
                                    msg_count = len(history)
                            except Exception:
                                created_at = "unknown"
                                updated_at = "unknown"
                                msg_count = 0

                            index_data[session_id] = {
                                "created_at": created_at,
                                "parent_id": None,
                                "alias": session_id,
                                "updated_at": updated_at,
                                "messages_count": msg_count
                            }
            return index_data

    @classmethod
    def load_session_history(cls, session_id):
        path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if not os.path.exists(path):
            return []
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

        file_lock = cls._get_file_lock(session_id)
        with file_lock:
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                os.replace(temp_path, path)
            except Exception as e:
                print(f"⚠️ 保存会话内容失败: {e}")
                return

        with cls._index_lock:
            index_data = cls.get_all_sessions()
            session_info = index_data.get(session_id, {})

            if not session_info.get("created_at") or session_info.get("created_at") == "unknown":
                session_info["created_at"] = time.strftime('%Y-%m-%d %H:%M:%S')

            if parent_id is not None:
                session_info["parent_id"] = parent_id
            if alias is not None:
                session_info["alias"] = alias

            if "parent_id" not in session_info:
                session_info["parent_id"] = None
            if "alias" not in session_info:
                session_info["alias"] = session_id

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
        cls.save_session(
            session_id=new_session_id,
            history=current_history,
            parent_id=current_session_id,
            alias=branch_alias
        )
        return new_session_id
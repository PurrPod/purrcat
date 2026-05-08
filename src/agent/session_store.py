import os
import json
import uuid
import time
import copy
import threading
from src.utils.config import SESSIONS_DIR, SESSION_INDEX_PATH


class SessionStore:
    """会话持久化与分支管理层 (Repository Pattern)"""
    _index_lock = threading.Lock()

    @staticmethod
    def _generate_id():
        return f"session_{uuid.uuid4().hex[:8]}"

    @classmethod
    def get_all_sessions(cls):
        """获取所有会话列表（用于构建 Git 树状图）"""
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
        """加载指定会话的历史记录"""
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
        """保存历史并安全更新索引 (支持临时文件替换，防断电损坏)"""
        path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        temp_path = f"{path}.tmp"
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
        """
        拉取分支核心逻辑：
        1. 生成新 ID
        2. 深拷贝当前内存历史
        3. 将拷贝存入新 ID 文件，建立父子关联
        """
        new_session_id = cls._generate_id()
        history_copy = copy.deepcopy(current_history)
        
        cls.save_session(
            session_id=new_session_id, 
            history=history_copy, 
            parent_id=current_session_id, 
            alias=branch_alias
        )
        return new_session_id

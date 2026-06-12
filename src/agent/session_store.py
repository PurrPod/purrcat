import json
import os
import threading
import time
import uuid

from src.utils.config import SESSION_INDEX_PATH, SESSIONS_DIR


class SessionStore:
    _index_lock = threading.RLock()
    _file_locks = {}
    _file_locks_lock = threading.Lock()

    @classmethod
    def _get_file_lock(cls, session_id):
        with cls._file_locks_lock:
            if session_id not in cls._file_locks:
                cls._file_locks[session_id] = threading.Lock()
            return cls._file_locks[session_id]

    @staticmethod
    def _generate_id():
        return f"session_{uuid.uuid4().hex[:8]}"

    @classmethod
    def load_global_memo(cls):
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
        """🌟 重构：极速版，仅读取 index.json，绝不扫盘遍历文件夹"""
        with cls._index_lock:
            if os.path.exists(SESSION_INDEX_PATH):
                try:
                    with open(SESSION_INDEX_PATH, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    print(f"⚠️ 读取索引失败: {e}")
            return {}

    @classmethod
    def background_sync_sessions(cls):
        """🌟 新增：由后台低优任务调用的对账方法，用于修复索引和文件夹不同步的问题"""
        with cls._index_lock:
            index_data = cls.get_all_sessions()
            if not os.path.exists(SESSIONS_DIR):
                return

            needs_save = False
            for item in os.listdir(SESSIONS_DIR):
                if not item.startswith("session_"):
                    continue
                session_dir = os.path.join(SESSIONS_DIR, item)
                if os.path.isdir(session_dir):
                    session_id = item
                    meta_path = os.path.join(session_dir, "meta.json")
                    main_path = os.path.join(session_dir, "main.json")

                    msg_count = 0
                    if os.path.exists(main_path):
                        try:
                            with open(main_path, "r", encoding="utf-8") as f:
                                msg_count = len(json.load(f))
                        except Exception:
                            pass

                    if session_id not in index_data:
                        created_at = time.strftime("%Y-%m-%d %H:%M:%S")
                        updated_at = created_at
                        alias = session_id
                        if os.path.exists(meta_path):
                            try:
                                with open(meta_path, "r", encoding="utf-8") as f:
                                    m_data = json.load(f)
                                    created_at = m_data.get("created_at", created_at)
                                    updated_at = m_data.get("updated_at", updated_at)
                                    alias = m_data.get("alias", alias)
                            except Exception:
                                pass

                        index_data[session_id] = {
                            "id": session_id,
                            "created_at": created_at,
                            "parent_id": None,
                            "alias": alias,
                            "updated_at": updated_at,
                            "messages_count": msg_count,
                        }
                        needs_save = True
                    else:
                        index_data[session_id]["messages_count"] = msg_count
                        if os.path.exists(meta_path):
                            try:
                                with open(meta_path, "r", encoding="utf-8") as f:
                                    m_data = json.load(f)
                                    if (
                                        "alias" in m_data
                                        and index_data[session_id].get("alias")
                                        != m_data["alias"]
                                    ):
                                        index_data[session_id]["alias"] = m_data[
                                            "alias"
                                        ]
                                        needs_save = True
                            except Exception:
                                pass

            if needs_save:
                try:
                    with open(SESSION_INDEX_PATH, "w", encoding="utf-8") as f:
                        json.dump(index_data, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

    @classmethod
    def load_session_history(cls, session_id, branch_id="main"):
        """🌟 重构：从会话文件夹内的特定分支文件加载历史"""
        filename = "main.json" if branch_id == "main" else f"sub_{branch_id}.json"
        path = os.path.join(SESSIONS_DIR, session_id, filename)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ 读取会话 {session_id} 分支 {branch_id} 失败: {e}")
            return []

    @classmethod
    def save_session(
        cls,
        session_id,
        history,
        branch_id="main",
        parent_id=None,
        alias=None,
        window_token=0,
        deliverable=None,
        action=None,
    ):
        """🌟 重构：线程安全地进行多文件分支隔离归档，并追溯分叉拓扑"""
        session_dir = os.path.join(SESSIONS_DIR, session_id)
        os.makedirs(session_dir, exist_ok=True)

        filename = "main.json" if branch_id == "main" else f"sub_{branch_id}.json"
        path = os.path.join(session_dir, filename)
        temp_path = f"{path}.tmp"

        file_lock = cls._get_file_lock(f"{session_id}_{branch_id}")
        with file_lock:
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                os.replace(temp_path, path)
            except Exception as e:
                print(f"⚠️ 保存分支 {branch_id} 失败: {e}")
                return

        # 更新文件夹内的拓扑元数据 meta.json
        meta_path = os.path.join(session_dir, "meta.json")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        meta_lock = cls._get_file_lock(f"{session_id}_meta")
        with meta_lock:
            meta_data = {
                "session_id": session_id,
                "created_at": timestamp,
                "branches": {},
            }
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta_data = json.load(f)
                except Exception:
                    pass

            meta_data["updated_at"] = timestamp
            if alias:
                meta_data["alias"] = alias
            if parent_id:
                meta_data["parent_id"] = parent_id

            if "branches" not in meta_data:
                meta_data["branches"] = {}

            if branch_id == "main":
                meta_data["branches"]["main"] = {
                    "status": "active",
                    "updated_at": timestamp,
                    "window_token": window_token,
                }
            else:
                meta_data["branches"][branch_id] = {
                    "status": "active"
                    if branch_id in meta_data.get("active_branches", {})
                    else "completed",
                    "fork_from": "main",
                    "deliverable": deliverable,
                    "action": action,
                    "updated_at": timestamp,
                }

            try:
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta_data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # 同步全局索引 index.json 保持 UI 完美渲染
        with cls._index_lock:
            index_data = cls.get_all_sessions()
            session_info = index_data.get(session_id, {})
            session_info["updated_at"] = timestamp
            session_info["messages_count"] = (
                len(history)
                if branch_id == "main"
                else session_info.get("messages_count", 0)
            )
            index_data[session_id] = session_info
            try:
                with open(SESSION_INDEX_PATH, "w", encoding="utf-8") as f:
                    json.dump(index_data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    @classmethod
    def create_branch(
        cls, current_session_id, current_history, branch_alias=None, window_token=0
    ):
        new_session_id = cls._generate_id()
        cls.save_session(
            session_id=new_session_id,
            history=current_history,
            parent_id=current_session_id,
            alias=branch_alias,
            window_token=window_token,
        )
        return new_session_id

    @classmethod
    def delete_branch(cls, session_id, branch_id):
        """删除单个分支（保护主干不被删除）"""
        if branch_id == "main":
            return False  # 保护主干不被这样删

        session_dir = os.path.join(SESSIONS_DIR, session_id)
        path = os.path.join(session_dir, f"sub_{branch_id}.json")

        # 1. 物理删除文件
        file_lock = cls._get_file_lock(f"{session_id}_{branch_id}")
        with file_lock:
            if os.path.exists(path):
                os.remove(path)

        # 2. 从 meta.json 拓扑中抹除
        meta_path = os.path.join(session_dir, "meta.json")
        meta_lock = cls._get_file_lock(f"{session_id}_meta")
        with meta_lock:
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta_data = json.load(f)
                    if "branches" in meta_data and branch_id in meta_data["branches"]:
                        del meta_data["branches"][branch_id]
                        with open(meta_path, "w", encoding="utf-8") as f:
                            json.dump(meta_data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"清理 meta.json 失败: {e}")
        return True

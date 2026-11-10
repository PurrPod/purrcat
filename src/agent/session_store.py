import os
import shutil
import threading
import time
import uuid

from src.agent.session_layout import (
    branch_path,
    filter_session_index,
    is_session_id,
    memo_path,
    meta_path,
    plan_path,
    read_json,
    session_dir,
    write_json,
    write_json_atomic,
)
from src.utils.config import SESSION_INDEX_PATH, SESSIONS_DIR


class SessionStore:
    # 每个会话一份 BrainStorm 总计划（@PLAN 引用读取它）
    PLAN_FILENAME = "plan.md"

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
    def get_plan_path(cls, session_id):
        """会话级 BrainStorm 计划文件的宿主机绝对路径。"""
        return plan_path(SESSIONS_DIR, session_id, cls.PLAN_FILENAME)

    @classmethod
    def save_session_plan(cls, session_id, content):
        """整体刷新某会话的 BrainStorm 总计划（每次 BrainStorm 调用后覆盖写入）。"""
        path = cls.get_plan_path(session_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp_path = f"{path}.tmp"
        with cls._get_file_lock(f"{session_id}_plan"):
            with open(temp_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            os.replace(temp_path, path)

    @classmethod
    def read_session_plan(cls, session_id):
        """读取某会话的 BrainStorm 总计划；不存在或读取失败时返回空串。"""
        path = cls.get_plan_path(session_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    @classmethod
    def load_global_memo(cls):
        path = memo_path(SESSIONS_DIR)
        if not os.path.exists(path):
            return []
        try:
            return read_json(path)
        except Exception as e:
            print(f"[Error] 读取全局 memo 失败: {e}")
            return []

    @classmethod
    def save_global_memo(cls, memo_list):
        path = memo_path(SESSIONS_DIR)
        with cls._index_lock:
            try:
                write_json_atomic(path, memo_list)
            except Exception as e:
                print(f"[Warn] 保存全局 memo 失败: {e}")

    @classmethod
    def get_all_sessions(cls):
        """🌟 重构：极速版，仅读取 index.json，绝不扫盘遍历文件夹"""
        with cls._index_lock:
            if os.path.exists(SESSION_INDEX_PATH):
                try:
                    return filter_session_index(read_json(SESSION_INDEX_PATH))
                except Exception as e:
                    print(f"[Warn] 读取索引失败: {e}")
            return {}

    @classmethod
    def delete_session(cls, session_id):
        """删除会话目录并同步索引（调用方负责拦截活跃会话）。"""
        directory = session_dir(SESSIONS_DIR, session_id)
        if os.path.isdir(directory):
            with cls._get_file_lock(session_id):
                shutil.rmtree(directory)
            print(f"[Delete] 已删除会话文件夹: {directory}")

        with cls._index_lock:
            if not os.path.exists(SESSION_INDEX_PATH):
                return
            try:
                index_data = read_json(SESSION_INDEX_PATH)
                if session_id in index_data:
                    del index_data[session_id]
                    write_json(SESSION_INDEX_PATH, index_data)
            except Exception as e:
                print(f"Error updating index: {e}")

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
                directory = session_dir(SESSIONS_DIR, item)
                if os.path.isdir(directory):
                    session_id = item
                    meta_file = meta_path(SESSIONS_DIR, session_id)
                    main_file = branch_path(SESSIONS_DIR, session_id, "main")

                    msg_count = 0
                    if os.path.exists(main_file):
                        try:
                            msg_count = len(read_json(main_file))
                        except Exception:
                            pass

                    if session_id not in index_data:
                        created_at = time.strftime("%Y-%m-%d %H:%M:%S")
                        updated_at = created_at
                        alias = session_id
                        project_id = ""
                        if os.path.exists(meta_file):
                            try:
                                m_data = read_json(meta_file)
                                created_at = m_data.get("created_at", created_at)
                                updated_at = m_data.get("updated_at", updated_at)
                                alias = m_data.get("alias", alias)
                                project_id = m_data.get("project_id", "")
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
                        if project_id:
                            index_data[session_id]["project_id"] = project_id
                        needs_save = True
                    else:
                        index_data[session_id]["messages_count"] = msg_count
                        if os.path.exists(meta_file):
                            try:
                                m_data = read_json(meta_file)
                                if (
                                    "alias" in m_data
                                    and index_data[session_id].get("alias")
                                    != m_data["alias"]
                                ):
                                    index_data[session_id]["alias"] = m_data["alias"]
                                    needs_save = True
                            except Exception:
                                pass

            if needs_save:
                try:
                    write_json(SESSION_INDEX_PATH, index_data)
                except Exception:
                    pass

    @classmethod
    def get_session_window_token(cls, session_id):
        """读取会话主干的上下文 Token 用量。

        权威来源是会话文件夹内的 meta.json（`branches.main.window_token`，
        由 save_session 落盘）；index.json 不保存该字段，故不能用 get_all_sessions。
        供 manager 在重启恢复 / 切换会话时还原 Token 圆环进度。
        """
        try:
            meta = read_json(meta_path(SESSIONS_DIR, session_id))
            return int(
                meta.get("branches", {}).get("main", {}).get("window_token", 0) or 0
            )
        except Exception:
            return 0

    @classmethod
    def get_session_consumed_tokens(cls, session_id):
        """读取会话累计 Token 消耗（贯通主干与所有子代理分支）。

        权威来源同样是会话文件夹内的 meta.json：遍历 branches，把主干
        （branch_id == "main"）计入 main，其余子代理分支计入 sub，
        返回 {"main", "sub", "total"}。异常时安全回退为全 0。
        """
        main_total, sub_total = 0, 0
        try:
            meta = read_json(meta_path(SESSIONS_DIR, session_id))
            branches = meta.get("branches", {}) or {}
            for bid, info in branches.items():
                value = int((info or {}).get("consumed_tokens", 0) or 0)
                if bid == "main":
                    main_total += value
                else:
                    sub_total += value
        except Exception:
            return {"main": 0, "sub": 0, "total": 0}
        return {"main": main_total, "sub": sub_total, "total": main_total + sub_total}

    @classmethod
    def load_session_history(cls, session_id, branch_id="main"):
        """🌟 重构：从会话文件夹内的特定分支文件加载历史"""
        path = branch_path(SESSIONS_DIR, session_id, branch_id)
        if not os.path.exists(path):
            return []
        try:
            return read_json(path)
        except Exception as e:
            print(f"[Error] 读取会话 {session_id} 分支 {branch_id} 失败: {e}")
            return []

    @classmethod
    def set_session_paradigm(cls, session_id, paradigm=None):
        """把某个会话绑定的范式写入 meta.json 与全局索引（None 表示回落默认，移除记录）。"""
        directory = session_dir(SESSIONS_DIR, session_id)
        os.makedirs(directory, exist_ok=True)
        meta_file = meta_path(SESSIONS_DIR, session_id)

        with cls._get_file_lock(f"{session_id}_meta"):
            meta_data = {}
            if os.path.exists(meta_file):
                try:
                    meta_data = read_json(meta_file)
                except Exception:
                    meta_data = {}
            if paradigm:
                meta_data["paradigm"] = paradigm
            else:
                meta_data.pop("paradigm", None)
            meta_data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            try:
                write_json(meta_file, meta_data)
            except Exception:
                pass

        with cls._index_lock:
            try:
                index_data = cls.get_all_sessions()
                session_info = index_data.get(session_id, {})
                if paradigm:
                    session_info["paradigm"] = paradigm
                else:
                    session_info.pop("paradigm", None)
                index_data[session_id] = session_info
                write_json(SESSION_INDEX_PATH, index_data)
            except Exception:
                pass

    @classmethod
    def set_session_project(cls, session_id, project_id=None):
        """把会话归入项目；project_id 为 None/空表示回到「未分类」。

        只改归属，不动 updated_at，避免把老会话顶到列表最前面。
        """
        if not is_session_id(session_id):
            raise ValueError("非法的会话 id")
        directory = session_dir(SESSIONS_DIR, session_id)
        os.makedirs(directory, exist_ok=True)
        meta_file = meta_path(SESSIONS_DIR, session_id)

        with cls._get_file_lock(f"{session_id}_meta"):
            meta_data = {}
            if os.path.exists(meta_file):
                try:
                    meta_data = read_json(meta_file) or {}
                except Exception:
                    meta_data = {}
            meta_data.setdefault("session_id", session_id)
            if project_id:
                meta_data["project_id"] = project_id
            else:
                meta_data.pop("project_id", None)
            try:
                write_json(meta_file, meta_data)
            except Exception as e:
                print(f"[Warn] 写入会话项目归属失败: {e}")

        with cls._index_lock:
            index_data = cls.get_all_sessions()
            session_info = index_data.get(session_id)
            if session_info is None:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                session_info = {
                    "id": session_id,
                    "alias": session_id,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "messages_count": 0,
                }
            if project_id:
                session_info["project_id"] = project_id
            else:
                session_info.pop("project_id", None)
            index_data[session_id] = session_info
            try:
                write_json(SESSION_INDEX_PATH, index_data)
            except Exception as e:
                print(f"[Warn] 更新会话索引失败: {e}")

    @classmethod
    def get_session_project(cls, session_id):
        """会话所属项目：以 meta.json 为准（索引可能滞后），缺失时回退索引。"""
        if not session_id:
            return None
        try:
            project_id = (read_json(meta_path(SESSIONS_DIR, session_id)) or {}).get(
                "project_id"
            )
            if project_id:
                return project_id
        except Exception:
            pass
        return cls.get_all_sessions().get(session_id, {}).get("project_id")

    @classmethod
    def save_session(
        cls,
        session_id,
        history,
        branch_id="main",
        parent_id=None,
        alias=None,
        paradigm=None,
        window_token=0,
        deliverable=None,
        action=None,
        consumed_tokens=None,
        project_id=None,
    ):
        """🌟 重构：线程安全地进行多文件分支隔离归档，并追溯分叉拓扑"""
        directory = session_dir(SESSIONS_DIR, session_id)
        os.makedirs(directory, exist_ok=True)

        path = branch_path(SESSIONS_DIR, session_id, branch_id)

        file_lock = cls._get_file_lock(f"{session_id}_{branch_id}")
        with file_lock:
            try:
                write_json_atomic(path, history)
            except Exception as e:
                print(f"[Warn] 保存分支 {branch_id} 失败: {e}")
                return

        # 更新文件夹内的拓扑元数据 meta.json
        meta_file = meta_path(SESSIONS_DIR, session_id)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        meta_lock = cls._get_file_lock(f"{session_id}_meta")
        with meta_lock:
            meta_data = {
                "session_id": session_id,
                "created_at": timestamp,
                "branches": {},
            }
            if os.path.exists(meta_file):
                try:
                    meta_data = read_json(meta_file)
                except Exception:
                    pass

            meta_data["updated_at"] = timestamp
            if alias:
                meta_data["alias"] = alias
            if paradigm:
                meta_data["paradigm"] = paradigm
            if parent_id:
                meta_data["parent_id"] = parent_id
            if project_id:
                meta_data["project_id"] = project_id

            if "branches" not in meta_data:
                meta_data["branches"] = {}

            if branch_id == "main":
                prev_main = meta_data["branches"].get("main", {}) or {}
                meta_data["branches"]["main"] = {
                    "status": "active",
                    "updated_at": timestamp,
                    "window_token": window_token,
                    # 未显式传入时保留旧值，避免其它调用方把累计消耗清零
                    "consumed_tokens": consumed_tokens
                    if consumed_tokens is not None
                    else prev_main.get("consumed_tokens", 0),
                }
            else:
                prev_sub = meta_data["branches"].get(branch_id, {}) or {}
                meta_data["branches"][branch_id] = {
                    "status": "active"
                    if branch_id in meta_data.get("active_branches", {})
                    else "completed",
                    "fork_from": "main",
                    "deliverable": deliverable,
                    "action": action,
                    "updated_at": timestamp,
                    "consumed_tokens": consumed_tokens
                    if consumed_tokens is not None
                    else prev_sub.get("consumed_tokens", 0),
                }

            try:
                write_json(meta_file, meta_data)
            except Exception:
                pass

        # 同步全局索引 index.json 保持 UI 完美渲染
        with cls._index_lock:
            index_data = cls.get_all_sessions()
            session_info = index_data.get(session_id, {})

            session_info["id"] = session_id  # 🌟 修复：确保新生会话有 ID
            session_info["updated_at"] = timestamp
            if alias:
                session_info["alias"] = alias  # 🌟 修复：创建时把自定义名字正确存入索引
            if paradigm:
                session_info["paradigm"] = paradigm

            session_info["messages_count"] = (
                len(history)
                if branch_id == "main"
                else session_info.get("messages_count", 0)
            )
            if project_id:
                session_info["project_id"] = project_id
            index_data[session_id] = session_info
            try:
                write_json(SESSION_INDEX_PATH, index_data)
            except Exception:
                pass

    @classmethod
    def create_branch(
        cls,
        current_session_id,
        current_history,
        branch_alias=None,
        paradigm=None,
        window_token=0,
        consumed_tokens=None,
        project_id=None,
    ):
        new_session_id = cls._generate_id()
        cls.save_session(
            session_id=new_session_id,
            history=current_history,
            parent_id=current_session_id,
            alias=branch_alias,
            paradigm=paradigm,
            window_token=window_token,
            consumed_tokens=consumed_tokens,
            project_id=project_id,
        )
        return new_session_id

    @classmethod
    def delete_branch(cls, session_id, branch_id):
        """删除单个分支（保护主干不被删除）"""
        if branch_id == "main":
            return False  # 保护主干不被这样删

        path = branch_path(SESSIONS_DIR, session_id, branch_id)

        # 1. 物理删除文件
        file_lock = cls._get_file_lock(f"{session_id}_{branch_id}")
        with file_lock:
            if os.path.exists(path):
                os.remove(path)

        # 2. 从 meta.json 拓扑中抹除
        meta_file = meta_path(SESSIONS_DIR, session_id)
        meta_lock = cls._get_file_lock(f"{session_id}_meta")
        with meta_lock:
            if os.path.exists(meta_file):
                try:
                    meta_data = read_json(meta_file)
                    if "branches" in meta_data and branch_id in meta_data["branches"]:
                        del meta_data["branches"][branch_id]
                        write_json(meta_file, meta_data)
                except Exception as e:
                    print(f"清理 meta.json 失败: {e}")
        return True

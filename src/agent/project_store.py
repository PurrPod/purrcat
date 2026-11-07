import json
import os
import shutil
import threading
import time
import uuid

from src.utils.config import PROJECT_INDEX_PATH, PROJECTS_DIR


class ProjectStore:
    """项目 = 会话分类器。

    存储结构：
      DATA_DIR/projects/index.json                 项目索引（id/name/created_at/updated_at）
      DATA_DIR/projects/<project_id>/MEMORY.md     项目记忆文件（由 Agent 在任务后自行维护）
    会话的归属写在会话自身的 meta.json 与全局 index.json 的 project_id 字段（缺省 = 未分类）。
    项目内新建会话时，系统提示只注入该 MEMORY.md 的绝对路径与维护方式，不注入正文。
    """

    MEMORY_FILENAME = "MEMORY.md"
    LEGACY_FILENAME = "PROJECT.md"  # 兼容旧项目文件，读取时自动迁移为 MEMORY.md

    _index_lock = threading.RLock()

    @staticmethod
    def _generate_id():
        return f"project_{uuid.uuid4().hex[:8]}"

    @classmethod
    def _valid_id(cls, project_id):
        pid = str(project_id or "")
        return pid.startswith("project_") and not any(
            c in pid for c in ("/", "\\", "..")
        )

    @classmethod
    def _project_dir(cls, project_id):
        return os.path.join(PROJECTS_DIR, project_id)

    @classmethod
    def memory_path(cls, project_id):
        return os.path.join(cls._project_dir(project_id), cls.MEMORY_FILENAME)

    @classmethod
    def _migrate_legacy(cls, project_id):
        """旧项目只有 PROJECT.md：无损改名为 MEMORY.md。"""
        legacy = os.path.join(cls._project_dir(project_id), cls.LEGACY_FILENAME)
        memory = cls.memory_path(project_id)
        if os.path.exists(legacy) and not os.path.exists(memory):
            try:
                os.replace(legacy, memory)
            except OSError as e:
                print(f"[Warn] 迁移项目记忆文件失败: {e}")

    @classmethod
    def _load_index(cls):
        with cls._index_lock:
            if os.path.exists(PROJECT_INDEX_PATH):
                try:
                    with open(PROJECT_INDEX_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f) or {}
                    projects = data.get("projects") if isinstance(data, dict) else {}
                    return projects if isinstance(projects, dict) else {}
                except Exception as e:
                    print(f"[Warn] 读取项目索引失败: {e}")
            return {}

    @classmethod
    def _save_index(cls, projects):
        with cls._index_lock:
            temp_path = f"{PROJECT_INDEX_PATH}.tmp"
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump({"projects": projects}, f, ensure_ascii=False, indent=2)
                os.replace(temp_path, PROJECT_INDEX_PATH)
            except Exception as e:
                print(f"[Warn] 保存项目索引失败: {e}")

    @classmethod
    def list_projects(cls):
        """按创建时间升序返回全部项目（老项目在上，列表顺序稳定）。"""
        projects = cls._load_index()
        items = [dict(v, id=k) for k, v in projects.items() if isinstance(v, dict)]
        for item in items:
            cls._migrate_legacy(item["id"])
        items.sort(
            key=lambda p: (str(p.get("created_at") or ""), str(p.get("id") or ""))
        )
        return items

    @classmethod
    def get_project(cls, project_id):
        if not cls._valid_id(project_id):
            return None
        item = cls._load_index().get(project_id)
        return dict(item, id=project_id) if isinstance(item, dict) else None

    @classmethod
    def create_project(cls, name):
        name = str(name or "").strip()
        if not name:
            raise ValueError("项目名称不能为空")
        project_id = cls._generate_id()
        folder = cls._project_dir(project_id)
        os.makedirs(folder, exist_ok=True)
        memory_path = cls.memory_path(project_id)
        # 不要求用户编辑：建项目只落一个带自身位置的记忆文件，后续由 Agent 维护
        with open(memory_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(
                f"# 项目记忆：{name}\n\n"
                f"本文件位于：`{memory_path}`\n\n"
                "用于记录本项目的长期约定、进度与待办，由 Agent 在完成任务后按需更新。\n"
            )
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        projects = cls._load_index()
        projects[project_id] = {
            "name": name,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        cls._save_index(projects)
        return dict(projects[project_id], id=project_id)

    @classmethod
    def update_project(cls, project_id, name=None):
        projects = cls._load_index()
        item = projects.get(project_id)
        if not isinstance(item, dict):
            return None
        if name is not None:
            name = str(name).strip()
            if not name:
                raise ValueError("项目名称不能为空")
            item["name"] = name
        item["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        cls._save_index(projects)
        return dict(item, id=project_id)

    @classmethod
    def prompt_block(cls, project_id):
        """项目内新建会话时追加进系统提示的片段：只给 MEMORY.md 位置与维护约定。"""
        info = cls.get_project(project_id)
        if not info:
            return ""
        cls._migrate_legacy(project_id)
        name = info.get("name") or project_id
        path = cls.memory_path(project_id)
        return (
            f"# 项目记忆：{name}\n\n"
            f"本会话属于项目「{name}」。项目记忆文件位于：{path}\n\n"
            "执行任务后，如有需要（例如补充项目约定、进度、待办或已确认的决策），"
            "请手动编辑上述 MEMORY.md；后续在该项目内新建的会话会继续沿用这份记忆。"
        )

    @classmethod
    def delete_project(cls, project_id):
        projects = cls._load_index()
        if project_id not in projects:
            return False
        projects.pop(project_id)
        cls._save_index(projects)
        folder = cls._project_dir(project_id)
        if os.path.isdir(folder):
            try:
                shutil.rmtree(folder)
            except Exception as e:
                print(f"[Warn] 删除项目目录失败: {e}")
        return True

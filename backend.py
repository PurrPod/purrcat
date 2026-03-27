import datetime
import uuid
from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import json
import os
import time
import threading
import shutil
import re
from typing import List, Optional, Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager
from collections import deque
import yaml

# Use absolute paths so the backend can find data/ even if started from a different cwd
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PLUGIN_COLLECTION_DIR = Path(os.path.join(BASE_DIR, "src", "plugins", "plugin_collection"))

# Import existing logic
from src.agent import agent as agent_module
from src.models import project as project_module
from src.models import task as task_module
from src.plugins.plugin_collection.filesystem.filesystem import set_allowed_directories, list_special_directories

# ====== 拥抱新架构：引入新版工具管理器 ======
from src.plugins.plugin_manager import init_tool, TOOL_INDEX_FILE, BASE_TOOLS
from src.plugins.plugin_collection.local_manager import register_plugin, unregister_plugin

from src.sensor.const import start_sensors
from src.sensor.feishu import start_lark_sensor


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup logic ---
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    os.environ.pop("http_proxy", None)
    os.environ.pop("https_proxy", None)

    # 1. 自动初始化基础插件 (仅在首次运行或 local_tool.yaml 丢失时)
    local_yaml = os.path.join(PLUGIN_COLLECTION_DIR, "local_tool.yaml")
    if not os.path.exists(local_yaml) or os.path.getsize(local_yaml) < 10:
        print("首次启动：自动注册核心基础插件...")
        for tool in ["database", "filesystem", "feishu", "manager", "schedule", "web", "mcptool", "multimodal"]:
            try:
                register_plugin(tool)
            except Exception as e:
                print(f"自动注册 {tool} 失败: {e}")

    # 2. 构建全局工具注册表 (替代旧版的各种手工加载)
    print("🔄 初始化全局工具注册表...")
    init_tool()

    # Set up filesystem
    try:
        config_path = os.path.join(DATA_DIR, "config", "file_config.json")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
                sandbox_dirs = config.get("sandbox_dirs", [])
            for test_dir in sandbox_dirs:
                if not os.path.exists(test_dir):
                    os.makedirs(test_dir, exist_ok=True)
            set_allowed_directories(sandbox_dirs)
    except Exception as e:
        print(f"Error setting up filesystem: {e}")

    try:
        print(list_special_directories())
    except Exception as e:
        print(f"Error listing special directories: {e}")

    start_sensors()

    _ensure_projects_loaded_from_checkpoints()
    _ensure_tasks_loaded_from_checkpoints()

    # Start Agent in a separate thread
    global agent
    agent = agent_module.Agent.load_checkpoint()
    agent_sensor_task = asyncio.create_task(asyncio.to_thread(agent.sensor))

    # Start Lark sensor with agent instance
    start_lark_sensor(agent)
    yield

    # --- Shutdown logic ---
    print("Shutting down backend...")
    try:
        agent.stop()
    except Exception:
        pass
    try:
        await asyncio.wait_for(agent_sensor_task, timeout=2)
    except Exception:
        try:
            agent_sensor_task.cancel()
        except Exception:
            pass


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Agent Backend API is running",
        "docs": "/docs",
        "frontend": "http://localhost:3000"
    }


# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_all_messages():
    messages = []
    temp_list = []
    while not agent_module.MESSAGE_QUEUE.empty():
        temp_list.append(agent_module.MESSAGE_QUEUE.get())

    for item in temp_list:
        agent_module.MESSAGE_QUEUE.put(item)
        msg = item[2].copy()
        msg["id"] = f"{item[0]}-{item[1]}"
        msg["timestamp"] = item[1]
        messages.append(msg)
    return messages


def remove_message_from_queue(msg_id: str):
    temp_list = []
    removed = False
    while not agent_module.MESSAGE_QUEUE.empty():
        item = agent_module.MESSAGE_QUEUE.get()
        current_id = f"{item[0]}-{item[1]}"
        if current_id == msg_id:
            removed = True
            continue
        temp_list.append(item)

    for item in temp_list:
        agent_module.MESSAGE_QUEUE.put(item)
    return removed


@app.get("/api/messages")
async def get_messages():
    return get_all_messages()


@app.delete("/api/messages/{msg_id}")
async def delete_message(msg_id: str):
    if remove_message_from_queue(msg_id):
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Message not found")


class MessageCreate(BaseModel):
    type: str
    content: str
    chat_id: Optional[str] = "owner"


@app.post("/api/messages")
async def create_message(msg: MessageCreate):
    agent_module.add_message(msg.dict())
    return {"status": "success"}


@app.get("/api/thought-chain")
async def get_thought_chain():
    return agent.current_history


class ForcePushRequest(BaseModel):
    content: str


@app.post("/api/agent/force-push")
async def force_push(request: ForcePushRequest):
    agent.force_push(request.content)
    return {"status": "success"}


@app.post("/api/agent/summarize-memory")
async def summarize_memory():
    agent._check_and_summarize_memory(check_mode=False)
    return {"status": "success"}


def _ensure_projects_loaded_from_checkpoints():
    base_dir = os.path.join(DATA_DIR, "checkpoints", "project")
    if not os.path.isdir(base_dir):
        return

    existing_ids = {p.get("id") for p in project_module.PROJECT_POOL}

    for entry in os.listdir(base_dir):
        checkpoint_path = os.path.join(base_dir, entry, "checkpoint.json")
        if not os.path.isfile(checkpoint_path):
            continue
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            continue

        project_id = state.get("id")
        if not project_id or project_id in existing_ids:
            continue

        now_iso = datetime.datetime.now().isoformat()
        progress = 0
        stage_histories = state.get('stage_histories', {})
        if 'summary' in stage_histories:
            progress = 100
        elif 'second_run_tasks' in stage_histories:
            progress = 75
        elif 'first_run_tasks' in stage_histories:
            progress = 50
        elif 'slice_tasks' in stage_histories:
            progress = 25
        else:
            progress = 10

        project_record = {
            "name": state.get("name", "Unknown"),
            "id": project_id,
            "state": state.get("state", "completed"),
            "creat_time": state.get("creat_time", entry.split("_")[-1] if "_" in entry else ""),
            "core": state.get("core"),
            "available_tools": state.get("available_tools", []),
            "available_workers": state.get("available_workers", []),
            "check_mode": state.get("check_mode", False),
            "refine_mode": state.get("refine_mode", False),
            "judge_mode": state.get("judge_mode", False),
            "is_agent": state.get("is_agent", False),
            "progress": progress,
            "createdAt": now_iso,
            "updatedAt": now_iso,
        }
        project_module.PROJECT_POOL.append(project_record)
        existing_ids.add(project_id)


def _ensure_tasks_loaded_from_checkpoints():
    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.isdir(base_dir):
        return

    existing_ids = {t.get("id") for t in task_module.TASK_POOL}

    for entry in os.listdir(base_dir):
        checkpoint_path = os.path.join(base_dir, entry, "checkpoint.json")
        if not os.path.isfile(checkpoint_path):
            continue
        try:
            task = task_module.Task.load_checkpoint(checkpoint_path)
            if task and task.task_id not in existing_ids:
                task_module.TASK_POOL.append({
                    "name": task.name,
                    "id": task.task_id,
                    "state": task.state if hasattr(task, 'state') else "completed",
                    "progress": 100 if task.run_result else 50,
                    "creat_time": task.creat_time,
                })
                existing_ids.add(task.task_id)
        except Exception:
            pass


@app.get("/api/projects")
async def get_projects():
    _ensure_projects_loaded_from_checkpoints()
    projects = []
    for p in project_module.PROJECT_POOL:
        project_data = p.copy()
        instance = project_module.PROJECT_INSTANCES.get(p["id"])
        if instance:
            project_data["history"] = instance.current_history
        projects.append(project_data)
    return projects


def _ensure_tasks_loaded_from_logs():
    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.isdir(base_dir):
        return

    existing_ids = {t.get("id") for t in task_module.TASK_POOL}

    for entry in os.listdir(base_dir):
        log_path = os.path.join(base_dir, entry, "log.jsonl")
        if not os.path.isfile(log_path):
            continue

        folder_name = entry
        task_name = folder_name
        creat_time = ""
        if "_" in folder_name:
            maybe_time = folder_name.split("_")[-1]
            task_name = folder_name[: -(len(maybe_time) + 1)] or folder_name
            creat_time = maybe_time

        task_id = None
        first_ts = None
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except Exception:
                        continue
                    if not task_id:
                        task_id = payload.get("task_id")
                    if not first_ts:
                        first_ts = payload.get("timestamp")
                    if task_id and first_ts:
                        break
        except Exception:
            continue

        if not task_id or task_id in existing_ids:
            continue

        created_iso = (
            datetime.datetime.fromtimestamp(first_ts).isoformat()
            if isinstance(first_ts, (int, float))
            else datetime.datetime.now().isoformat()
        )

        task_record = {
            "name": task_name or "Unknown",
            "id": task_id,
            "state": "running",
            "creat_time": creat_time,
            "progress": 50,
            "createdAt": created_iso,
            "updatedAt": created_iso,
        }
        task_module.TASK_POOL.append(task_record)
        existing_ids.add(task_id)


@app.get("/api/tasks")
async def get_tasks():
    _ensure_tasks_loaded_from_checkpoints()
    _ensure_tasks_loaded_from_logs()

    task_map = {}
    for t in task_module.TASK_POOL:
        task_id = t.get("id")
        if not task_id:
            continue
        task_data = t.copy()
        instance = task_module.TASK_INSTANCES.get(task_id)
        if instance:
            task_data["history"] = instance.current_history
        task_map[task_id] = task_data
    return list(task_map.values())


PROJECT_LOG_PATH_CACHE: Dict[str, str] = {}
PROJECT_CHECKPOINT_PATH_CACHE: Dict[str, str] = {}
LOG_READ_LOCK = threading.Lock()
PROJECT_LOG_READ_CACHE: Dict[str, Dict[str, Any]] = {}
TASK_LOG_READ_CACHE: Dict[str, Dict[str, Any]] = {}


def _resolve_project_log_path(project_id: str) -> Optional[str]:
    cached = PROJECT_LOG_PATH_CACHE.get(project_id)
    if cached:
        return cached

    instance = project_module.PROJECT_INSTANCES.get(project_id)
    if instance:
        log_dir = os.path.join(DATA_DIR, "checkpoints", "project", f"{instance.name}_{instance.creat_time}")
        log_path = os.path.join(log_dir, "log.jsonl")
        PROJECT_LOG_PATH_CACHE[project_id] = log_path
        return log_path

    base_dir = os.path.join(DATA_DIR, "checkpoints", "project")
    if not os.path.isdir(base_dir):
        return None

    try:
        for entry in os.listdir(base_dir):
            checkpoint_path = os.path.join(base_dir, entry, "checkpoint.json")
            if not os.path.isfile(checkpoint_path):
                continue
            try:
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                if state.get("id") == project_id:
                    log_path = os.path.join(base_dir, entry, "log.jsonl")
                    PROJECT_LOG_PATH_CACHE[project_id] = log_path
                    return log_path
            except Exception:
                continue
    except Exception:
        return None
    return None


def _resolve_project_checkpoint_path(project_id: str) -> Optional[str]:
    cached = PROJECT_CHECKPOINT_PATH_CACHE.get(project_id)
    if cached:
        return cached

    instance = project_module.PROJECT_INSTANCES.get(project_id)
    if instance:
        checkpoint_dir = os.path.join(DATA_DIR, "checkpoints", "project", f"{instance.name}_{instance.creat_time}")
        checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.json")
        PROJECT_CHECKPOINT_PATH_CACHE[project_id] = checkpoint_path
        return checkpoint_path

    base_dir = os.path.join(DATA_DIR, "checkpoints", "project")
    if not os.path.isdir(base_dir):
        return None

    try:
        for entry in os.listdir(base_dir):
            checkpoint_path = os.path.join(base_dir, entry, "checkpoint.json")
            if not os.path.isfile(checkpoint_path):
                continue
            try:
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                if state.get("id") == project_id:
                    PROJECT_CHECKPOINT_PATH_CACHE[project_id] = checkpoint_path
                    return checkpoint_path
            except Exception:
                continue
    except Exception:
        return None
    return None


def _read_jsonl_entries(log_path, cache, cache_key, id_prefix, cursor, limit, tail):
    if tail:
        dq = deque(maxlen=limit)
        line_idx = 0
        offset = 0
        with open(log_path, "rb") as f:
            while True:
                b = f.readline()
                if not b:
                    break
                offset = f.tell()
                line = b.decode("utf-8", "replace").strip()
                if not line:
                    line_idx += 1
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    payload = {"card_type": "error", "content": line, "metadata": {"level": "warning"}}
                payload["id"] = f"{id_prefix}:{line_idx}"
                dq.append(payload)
                line_idx += 1
        with LOG_READ_LOCK:
            cache[cache_key] = {"path": log_path, "cursor": line_idx, "offset": offset}
        return {"entries": list(dq), "nextCursor": line_idx, "exists": True}

    with LOG_READ_LOCK:
        state = cache.get(cache_key) or {}
        cached_path = state.get("path")
        cached_cursor = state.get("cursor")
        cached_offset = state.get("offset")

    if cached_path == log_path and isinstance(cached_cursor, int) and isinstance(cached_offset,
                                                                                 int) and cached_cursor == cursor:
        entries = []
        line_idx = cursor
        offset = cached_offset
        with open(log_path, "rb") as f:
            try:
                f.seek(offset)
            except Exception:
                f.seek(0)
                line_idx = 0
            while len(entries) < limit:
                b = f.readline()
                if not b:
                    break
                offset = f.tell()
                line = b.decode("utf-8", "replace").strip()
                if not line:
                    line_idx += 1
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    payload = {"card_type": "error", "content": line, "metadata": {"level": "warning"}}
                payload["id"] = f"{id_prefix}:{line_idx}"
                entries.append(payload)
                line_idx += 1
        with LOG_READ_LOCK:
            cache[cache_key] = {"path": log_path, "cursor": line_idx, "offset": offset}
        return {"entries": entries, "nextCursor": line_idx, "exists": True}

    entries = []
    line_idx = 0
    offset = 0
    with open(log_path, "rb") as f:
        while line_idx < cursor:
            b = f.readline()
            if not b:
                break
            line_idx += 1
        offset = f.tell()
        while len(entries) < limit:
            b = f.readline()
            if not b:
                break
            offset = f.tell()
            line = b.decode("utf-8", "replace").strip()
            if not line:
                line_idx += 1
                continue
            try:
                payload = json.loads(line)
            except Exception:
                payload = {"card_type": "error", "content": line, "metadata": {"level": "warning"}}
            payload["id"] = f"{id_prefix}:{line_idx}"
            entries.append(payload)
            line_idx += 1
    with LOG_READ_LOCK:
        cache[cache_key] = {"path": log_path, "cursor": line_idx, "offset": offset}
    return {"entries": entries, "nextCursor": line_idx, "exists": True}


@app.get("/api/projects/dirty")
async def get_dirty_projects(clear: bool = True):
    with project_module.set_lock:
        dirty = list(project_module.dirty_projects)
        if clear:
            project_module.dirty_projects.clear()
    return {"dirty": dirty}


@app.get("/api/projects/{project_id}/log")
async def get_project_log(project_id: str, cursor: int = 0, limit: int = 500, tail: bool = False):
    if cursor < 0: cursor = 0
    if limit < 1: limit = 1
    if limit > 2000: limit = 2000

    log_path = _resolve_project_log_path(project_id)
    if not log_path or not os.path.exists(log_path):
        return {"entries": [], "nextCursor": cursor, "exists": False}
    try:
        return _read_jsonl_entries(log_path, PROJECT_LOG_READ_CACHE, project_id, project_id, cursor, limit, tail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ProjectAnswer(BaseModel):
    answer: str


@app.post("/api/projects/{project_id}/answer")
async def answer_project(project_id: str, payload: ProjectAnswer):
    queue = project_module.USER_QA_QUEUE.get(project_id)
    if not queue:
        raise HTTPException(status_code=404, detail="No pending question for this project")
    if queue.get("answers") is not None:
        return {"status": "already_answered"}
    queue["answers"] = {"用户回复": payload.answer}
    return {"status": "success"}


@app.post("/api/projects/{project_id}/stop")
async def stop_project_endpoint(project_id: str):
    if project_module.kill_project(project_id):
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Project not found")


@app.post("/api/projects/{project_id}/resume")
async def resume_project_endpoint(project_id: str):
    _ensure_projects_loaded_from_checkpoints()

    instance = project_module.PROJECT_INSTANCES.get(project_id)
    if instance:
        runner = getattr(instance, "_runner_thread", None)
        if runner and getattr(runner, "is_alive", None) and runner.is_alive():
            return {"status": "already_running"}

    checkpoint_path = _resolve_project_checkpoint_path(project_id)
    if not checkpoint_path or not os.path.isfile(checkpoint_path):
        raise HTTPException(status_code=404, detail="Project checkpoint not found")

    project = project_module.Project.load_checkpoint(checkpoint_path)
    project._killed = False
    project_module.set_project_state(project.id, "running")

    def _run_project():
        try:
            result = project.run_pipeline()
            agent_module.add_message(
                {"type": "project_message", "content": f"[Project通知] 项目 {project_id} 执行结束。\n结论: {result}"})
        except Exception as e:
            agent_module.add_message(
                {"type": "project_message", "content": f"\n[Project异常] 项目 {project_id} 运行时崩溃: {e}"})

    t = threading.Thread(target=_run_project, daemon=True)
    project._runner_thread = t
    t.start()
    return {"status": "success"}


@app.delete("/api/projects/{project_id}")
async def remove_project_endpoint(project_id: str):
    project_module.kill_project(project_id)
    project_module.delete_project(project_id)
    return {"status": "success"}


TASK_LOG_PATH_CACHE: Dict[str, str] = {}


def _resolve_task_log_path(task_id: str) -> Optional[str]:
    cached = TASK_LOG_PATH_CACHE.get(task_id)
    if cached:
        return cached

    instance = task_module.TASK_INSTANCES.get(task_id)
    if instance:
        log_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{instance.name}_{instance.creat_time}")
        log_path = os.path.join(log_dir, "log.jsonl")
        if os.path.exists(log_path):
            TASK_LOG_PATH_CACHE[task_id] = log_path
            return log_path

    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.isdir(base_dir):
        return None

    try:
        for entry in os.listdir(base_dir):
            log_path = os.path.join(base_dir, entry, "log.jsonl")
            if not os.path.isfile(log_path):
                continue
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        try:
                            payload = json.loads(line)
                        except Exception:
                            continue
                        if payload.get("task_id") == task_id:
                            TASK_LOG_PATH_CACHE[task_id] = log_path
                            return log_path
            except Exception:
                pass
            if entry == task_id or task_id in entry:
                TASK_LOG_PATH_CACHE[task_id] = log_path
                return log_path
        return None
    except Exception:
        return None
    return None


@app.get("/api/tasks/dirty")
async def get_dirty_tasks(clear: bool = True):
    with task_module.task_set_lock:
        dirty = list(task_module.dirty_tasks)
        if clear:
            task_module.dirty_tasks.clear()
    return {"dirty": dirty}


@app.get("/api/tasks/{task_id}/log")
async def get_task_log(task_id: str, cursor: int = 0, limit: int = 500, tail: bool = False):
    if cursor < 0: cursor = 0
    if limit < 1: limit = 1
    if limit > 2000: limit = 2000

    log_path = _resolve_task_log_path(task_id)
    if not log_path or not os.path.exists(log_path):
        return {"entries": [], "nextCursor": cursor, "exists": False}
    try:
        return _read_jsonl_entries(log_path, TASK_LOG_READ_CACHE, task_id, task_id, cursor, limit, tail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks/{task_id}/inject")
async def inject_task(task_id: str, request: ForcePushRequest):
    if task_module.inject_task_instruction(task_id, request.content):
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/api/tasks/{task_id}")
async def remove_task_endpoint(task_id: str):
    task_module.kill_task(task_id)
    task_module.delete_task(task_id)
    return {"status": "success"}


@app.get("/api/files")
async def get_files(path: str):
    allowed_files = {
        "user_profile": "src/agent/core/user_profile.md",
        "me": "src/agent/core/me.md",
        "soul": "src/agent/SOUL.md"
    }
    if path not in allowed_files:
        raise HTTPException(status_code=403, detail="File not allowed")

    file_path = allowed_files[path]
    if not os.path.exists(file_path):
        return {"content": ""}
    with open(file_path, "r", encoding="utf-8") as f:
        return {"content": f.read()}


class FileUpdate(BaseModel):
    content: str


@app.post("/api/files")
async def update_file(path: str, update: FileUpdate):
    allowed_files = {
        "user_profile": "src/agent/core/user_profile.md",
        "me": "src/agent/core/me.md",
        "soul": "src/agent/SOUL.md"
    }
    if path not in allowed_files:
        raise HTTPException(status_code=403, detail="File not allowed")

    file_path = allowed_files[path]
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(update.content)
    return {"status": "success"}


class ProjectCreate(BaseModel):
    name: str
    prompt: str
    core: str
    check_mode: bool = False
    refine_mode: bool = False
    judge_mode: bool = False
    is_agent: bool = True


@app.post("/api/projects")
async def create_project_endpoint(project: ProjectCreate):
    from src.plugins.plugin_collection.manager.manager import add_project
    try:
        msg = add_project(
            name=project.name,
            prompt=project.prompt,
            core=project.core,
            check_mode=project.check_mode,
            refine_mode=project.refine_mode,
            judge_mode=project.judge_mode,
            is_agent=project.is_agent
        )
        return {"status": "success", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/plugins/upload")
async def upload_plugin(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    first_file_path = Path(files[0].filename)
    plugin_name = first_file_path.parts[0]

    if not re.match(r"^[a-zA-Z0-9-]+$", plugin_name):
        raise HTTPException(status_code=400, detail=f"Invalid plugin name '{plugin_name}'.")

    plugin_dir = PLUGIN_COLLECTION_DIR / plugin_name
    if plugin_dir.exists():
        raise HTTPException(status_code=409, detail=f"Plugin '{plugin_name}' already exists.")

    temp_dir = Path("temp_plugin_upload")
    temp_dir.mkdir(exist_ok=True)
    temp_plugin_path = temp_dir / plugin_name
    temp_plugin_path.mkdir(exist_ok=True)

    has_init_yaml = False

    try:
        for file in files:
            file_path = Path(file.filename)
            save_path = temp_dir / file_path
            save_path.parent.mkdir(parents=True, exist_ok=True)

            with save_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            if file_path.name == "init.yaml" and len(file_path.parts) == 2:
                has_init_yaml = True

        if not has_init_yaml:
            raise HTTPException(status_code=400, detail="The plugin must contain an 'init.yaml'.")

        shutil.move(str(temp_plugin_path), str(PLUGIN_COLLECTION_DIR))

        try:
            # 注册新插件并立即刷新全局缓存
            register_plugin(plugin_name)
            init_tool()
        except Exception as e:
            print(f"Warning: Plugin '{plugin_name}' uploaded but failed to register: {e}")

        return {"status": "success", "message": f"Plugin '{plugin_name}' installed successfully."}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


@app.delete("/api/plugins/{plugin_name}")
async def unregister_plugin_endpoint(plugin_name: str):
    if not re.match(r"^[a-zA-Z0-9-]+$", plugin_name) or ".." in plugin_name:
        raise HTTPException(status_code=400, detail="Invalid plugin name.")
    try:
        unregister_plugin(plugin_name)
        init_tool()  # 刷新全局索引
        return {"status": "success", "message": "Plugin unregistered successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unregister plugin: {e}")


# ====== 获取所有工具大重构：完美兼容 Local + MCP ======
@app.get("/api/tools")
async def get_tools():
    """获取所有工具信息（支持 Local 和 MCP），直读全局注册表."""
    try:
        tools_list = []
        if os.path.exists(TOOL_INDEX_FILE):
            with open(TOOL_INDEX_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        tools_list.append(json.loads(line))

        # 按 plugin/server 进行聚合
        grouped = {}
        for t in tools_list:
            p_name = t["plugin"]
            if p_name not in grouped:
                grouped[p_name] = {
                    "name": p_name,
                    "description": f"[{t['route'].upper()}] 插件/服务",
                    "tools": []
                }
            grouped[p_name]["tools"].append({
                "name": t["func"],
                "description": t["desc"]
            })

        # 加上核心基础工具
        base_plugin = {
            "name": "system_core",
            "description": "[CORE] 系统核心指令",
            "tools": []
        }
        for bt in BASE_TOOLS:
            base_plugin["tools"].append({
                "name": bt["function"]["name"],
                "description": bt["function"]["description"]
            })

        result = [base_plugin] + list(grouped.values())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load tools: {e}")


@app.get("/api/plugins")
async def get_plugins():
    plugins = []
    local_yaml = os.path.join(PLUGIN_COLLECTION_DIR, "local_tool.yaml")
    active_plugins = {}
    if os.path.exists(local_yaml):
        with open(local_yaml, "r", encoding="utf-8") as f:
            active_plugins = yaml.safe_load(f) or {}

    if os.path.exists(PLUGIN_COLLECTION_DIR):
        for name in os.listdir(PLUGIN_COLLECTION_DIR):
            full_path = os.path.join(PLUGIN_COLLECTION_DIR, name)
            if os.path.isdir(full_path) and not name.startswith("__"):
                plugins.append({
                    "name": name,
                    "enabled": name in active_plugins,
                    "path": full_path
                })
    return plugins


@app.post("/api/plugins/{name}/toggle")
async def toggle_plugin(name: str):
    local_yaml = os.path.join(PLUGIN_COLLECTION_DIR, "local_tool.yaml")
    active_plugins = {}
    if os.path.exists(local_yaml):
        with open(local_yaml, "r", encoding="utf-8") as f:
            active_plugins = yaml.safe_load(f) or {}

    if name in active_plugins:
        unregister_plugin(name)
        init_tool()  # 刷新工具列表
        return {"enabled": False}
    else:
        register_plugin(name)
        init_tool()  # 刷新工具列表
        return {"enabled": True}


class TaskCreate(BaseModel):
    title: str
    desc: str
    deliverable: str
    prompt: str
    judge_mode: bool = False
    task_histories: str = ""
    core: str = "core"


@app.post("/api/tasks")
async def create_task_endpoint(task: TaskCreate):
    from src.plugins.plugin_collection.manager.manager import add_simple_task
    try:
        msg = add_simple_task(
            title=task.title,
            desc=task.desc,
            deliverable=task.deliverable,
            prompt=task.prompt,
            judge_mode=task.judge_mode,
            task_histories=task.task_histories,
            core=task.core
        )
        return {"status": "success", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config")
async def get_config():
    config_dir = "data/config"
    configs = {}
    if os.path.exists(config_dir):
        for filename in os.listdir(config_dir):
            if filename.endswith(".json"):
                with open(os.path.join(config_dir, filename), "r", encoding="utf-8") as f:
                    configs[filename] = json.load(f)
    return configs


def _load_schedule_paths():
    try:
        with open("data/config/config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
        schedule_file = cfg.get("schedule_daily", "data/schedule/schedule.json")
        cron_file = cfg.get("schedule_cron", "data/schedule/cron.json")
    except Exception:
        schedule_file = "data/schedule/schedule.json"
        cron_file = "data/schedule/cron.json"
    return schedule_file, cron_file


def _read_json_file(path: str, default=None):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _write_json_file(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class ScheduleItem(BaseModel):
    title: str
    start_time: str
    end_time: Optional[str] = None
    description: Optional[str] = None


class AlarmItem(BaseModel):
    title: str
    trigger_time: str
    repeat_rule: str = "none"
    active: bool = True


@app.get("/api/schedule")
async def get_schedule():
    schedule_file, _ = _load_schedule_paths()
    return _read_json_file(schedule_file, [])


@app.post("/api/schedule")
async def add_schedule(item: ScheduleItem):
    schedule_file, _ = _load_schedule_paths()
    schedules = _read_json_file(schedule_file, []) or []
    new_item = item.dict()
    new_item["id"] = str(uuid.uuid4())
    new_item["createdAt"] = datetime.datetime.now().isoformat()
    schedules.append(new_item)
    _write_json_file(schedule_file, schedules)
    return {"status": "success", "item": new_item}


@app.delete("/api/schedule/{item_id}")
async def delete_schedule(item_id: str):
    schedule_file, _ = _load_schedule_paths()
    schedules = _read_json_file(schedule_file, []) or []
    schedules = [s for s in schedules if s.get("id") != item_id]
    _write_json_file(schedule_file, schedules)
    return {"status": "success"}


@app.get("/api/cron")
async def get_cron():
    _, cron_file = _load_schedule_paths()
    return _read_json_file(cron_file, [])


@app.post("/api/cron")
async def add_cron(item: AlarmItem):
    _, cron_file = _load_schedule_paths()
    crons = _read_json_file(cron_file, []) or []
    new_item = item.dict()
    new_item["id"] = str(uuid.uuid4())
    new_item["createdAt"] = datetime.datetime.now().isoformat()
    crons.append(new_item)
    _write_json_file(cron_file, crons)
    return {"status": "success", "item": new_item}


@app.delete("/api/cron/{item_id}")
async def delete_cron(item_id: str):
    _, cron_file = _load_schedule_paths()
    crons = _read_json_file(cron_file, []) or []
    crons = [c for c in crons if c.get("id") != item_id]
    _write_json_file(cron_file, crons)
    return {"status": "success"}


@app.post("/api/cron/{item_id}")
async def update_cron_endpoint(item_id: str, updates: dict):
    _, cron_file = _load_schedule_paths()
    crons = _read_json_file(cron_file, []) or []
    updated = False
    for c in crons:
        if c.get("id") == item_id:
            for key in ["title", "trigger_time", "repeat_rule", "active"]:
                if key in updates:
                    c[key] = updates[key]
            updated = True
            break
    if updated:
        _write_json_file(cron_file, crons)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Alarm not found")


@app.post("/api/config/{filename}")
async def update_config(filename: str, config: Dict[str, Any]):
    if not filename.endswith(".json"):
        filename += ".json"
    file_path = os.path.join(DATA_DIR, "config", filename)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    return {"status": "success"}


@app.get("/api/skills")
async def get_skills():
    skill_dir = "data/skill"
    skills = []
    if os.path.exists(skill_dir):
        for name in os.listdir(skill_dir):
            if os.path.isdir(os.path.join(skill_dir, name)):
                skills.append({
                    "name": name,
                    "path": os.path.join(skill_dir, name)
                })
    return skills


@app.get("/api/databases")
async def get_databases():
    from src.plugins.plugin_collection.database.database import list_databases
    res = list_databases()
    return json.loads(res)["content"]["available_databases"]


if __name__ == "__main__":
    import uvicorn
    import logging

    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
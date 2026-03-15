import datetime
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import json
import os
import time
from typing import List, Optional, Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager

# Use absolute paths so the backend can find data/ even if started from a different cwd
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Import existing logic
from src.agent import agent as agent_module
from src.models import project as project_module
from src.models import task as task_module
from src.plugins.plugin_collection.filesystem.filesystem import set_allowed_directories, list_special_directories
from src.plugins.plugin_manager import register_plugin, get_plugin_config, GLOBAL_TOOL_YAML, PLUGIN_COLLECTION_DIR, load_global_tool_yaml, get_config_data
from src.sensor.const import start_sensors
from src.sensor.feishu import start_lark_sensor
import yaml

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup logic (mirroring main.py) ---
    # Clear proxy env vars to avoid Lark connection issues if proxy is down
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    os.environ.pop("http_proxy", None)
    os.environ.pop("https_proxy", None)
    
    # Register plugins
    for tool in ["database", "filesystem", "feishu", "manager", "schedule", "web"]:
        try:
            register_plugin(tool)
        except Exception as e:
            print(f"Error registering plugin {tool}: {e}")
            
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
     
    # Try listing special directories
    try:
        print(list_special_directories())
    except Exception as e:
        print(f"Error listing special directories: {e}")
        
    start_sensors()
    
    # Load checkpoints
    _ensure_projects_loaded_from_checkpoints()
    _ensure_tasks_loaded_from_checkpoints()
    
    # Start Agent in a separate thread
    global agent
    agent = agent_module.Agent.load_checkpoint()
    asyncio.create_task(asyncio.to_thread(agent.sensor))
    
    # Start Lark sensor with agent instance
    start_lark_sensor(agent)
    yield
    # --- Shutdown logic ---
    print("Shutting down backend...")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Agent Backend API is running",
        "docs": "/docs",
        "frontend": "http://localhost:3000"
    }

# Enable CORS for Next.js
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper function to get messages from PriorityQueue without popping
def get_all_messages():
    # PriorityQueue doesn't support viewing without popping
    # We'll temporarily empty it and refill it
    messages = []
    temp_list = []
    while not agent_module.MESSAGE_QUEUE.empty():
        temp_list.append(agent_module.MESSAGE_QUEUE.get())
    
    for item in temp_list:
        agent_module.MESSAGE_QUEUE.put(item)
        # item is (-priority, timestamp, message_dict)
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

# API Endpoints
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
    # Return history as thought chain
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
    """Scan data/checkpoints/project to backfill PROJECT_POOL after backend restart."""
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
        # 这里尊重 checkpoint 中保存的真实状态（running/completed/error/killed 等），
        # 具体的展示含义由前端再做一次映射。
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
    """Scan data/checkpoints/task to backfill TASK_POOL after backend restart."""
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
        except Exception as e:
            print(f"Error loading task checkpoint {checkpoint_path}: {e}")


@app.get("/api/projects")
async def get_projects():
    _ensure_projects_loaded_from_checkpoints()
    projects = []
    for p in project_module.PROJECT_POOL:
        project_data = p.copy()
        # Add history if instance exists
        instance = project_module.PROJECT_INSTANCES.get(p["id"])
        if instance:
            project_data["history"] = instance.current_history
        projects.append(project_data)
    return projects

@app.get("/api/tasks")
async def get_tasks():
    # Ensure tasks are backfilled from disk when backend restarts.
    # Some tasks only have log.jsonl (no checkpoint.json), so we need both methods.
    _ensure_tasks_loaded_from_checkpoints()
    _ensure_tasks_loaded_from_logs()

    # De-duplicate by task_id (防止出现重复key导致前端报错)
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

@app.get("/api/projects/dirty")
async def get_dirty_projects(clear: bool = True):
    with project_module.set_lock:
        dirty = list(project_module.dirty_projects)
        if clear:
            project_module.dirty_projects.clear()
    return {"dirty": dirty}

@app.get("/api/projects/{project_id}/log")
async def get_project_log(project_id: str, cursor: int = 0, limit: int = 500):
    if cursor < 0:
        cursor = 0
    if limit < 1:
        limit = 1
    if limit > 2000:
        limit = 2000

    log_path = _resolve_project_log_path(project_id)
    if not log_path or not os.path.exists(log_path):
        return {"entries": [], "nextCursor": cursor, "exists": False}

    entries: List[Dict[str, Any]] = []
    next_cursor = cursor

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                if idx < cursor:
                    continue
                if len(entries) >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    payload = {"card_type": "error", "content": line, "metadata": {"level": "warning"}}
                payload["id"] = f"{project_id}:{idx}"
                entries.append(payload)
                next_cursor = idx + 1
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"entries": entries, "nextCursor": next_cursor, "exists": True}

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

@app.delete("/api/projects/{project_id}")
async def remove_project_endpoint(project_id: str):
    project_module.kill_project(project_id)
    project_module.delete_project(project_id)
    return {"status": "success"}

TASK_LOG_PATH_CACHE: Dict[str, str] = {}


def _ensure_tasks_loaded_from_logs():
    """Scan data/checkpoints/task to backfill TASK_POOL after backend restart."""
    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.isdir(base_dir):
        return

    existing_ids = {t.get("id") for t in task_module.TASK_POOL}

    for entry in os.listdir(base_dir):
        log_path = os.path.join(base_dir, entry, "log.jsonl")
        if not os.path.isfile(log_path):
            continue

        # Derive task name and create time from folder name: <name>_<YYYYmmddHHMMSS>
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
                    # If we've found both identifying pieces, stop scanning.
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
            # 对于只有日志而没有 checkpoint 的任务，我们无法确定它是否真的完成。
            # 使用 running/50 作为默认状态，避免错误地显示为“已完成”。
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
    # 确保重启后磁盘中的 task 也能回填到内存池
    _ensure_tasks_loaded_from_logs()
    tasks = []
    for t in task_module.TASK_POOL:
        task_data = t.copy()
        # Add history if instance exists
        instance = task_module.TASK_INSTANCES.get(t.get("id"))
        if instance:
            task_data["history"] = instance.current_history
        tasks.append(task_data)
    return tasks


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
        # If the folder/time is stale (e.g. creat_time changed), fall back to scan to find the real log file

    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.isdir(base_dir):
        return None

    try:
        for entry in os.listdir(base_dir):
            log_path = os.path.join(base_dir, entry, "log.jsonl")
            if not os.path.isfile(log_path):
                continue

            # 1) 常规：通过 log 内容中的 task_id 查找
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
                        if payload.get("task_id") == task_id:
                            TASK_LOG_PATH_CACHE[task_id] = log_path
                            return log_path
            except Exception:
                pass

            # 2) 兼容：folder 名称可能就是 task_id（或包含 task_id），直接使用
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
async def get_task_log(task_id: str, cursor: int = 0, limit: int = 500):
    if cursor < 0:
        cursor = 0
    if limit < 1:
        limit = 1
    if limit > 2000:
        limit = 2000

    log_path = _resolve_task_log_path(task_id)
    if not log_path or not os.path.exists(log_path):
        return {"entries": [], "nextCursor": cursor, "exists": False}

    entries: List[Dict[str, Any]] = []
    next_cursor = cursor

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                if idx < cursor:
                    continue
                if len(entries) >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    payload = {"card_type": "error", "content": line, "metadata": {"level": "warning"}}
                payload["id"] = f"{task_id}:{idx}"
                entries.append(payload)
                next_cursor = idx + 1
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"entries": entries, "nextCursor": next_cursor, "exists": True}

@app.post("/api/tasks/{task_id}/inject")
async def inject_task(task_id: str, request: ForcePushRequest):
    print(f"[DEBUG] Inject task {task_id} with {request.content}")
    if task_module.inject_task_instruction(task_id, request.content):
        print(f"[DEBUG] Inject success")
        return {"status": "success"}
    print(f"[DEBUG] Inject failed")
    raise HTTPException(status_code=404, detail="Task not found")

@app.delete("/api/tasks/{task_id}")
async def remove_task_endpoint(task_id: str):
    task_module.kill_task(task_id)
    task_module.delete_task(task_id)
    return {"status": "success"}

@app.get("/api/files")
async def get_files(path: str):
    # Allowed files: user_profile.md, me.md, SOUL.md
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
    available_tools: List[str] = []

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
            is_agent=project.is_agent,
            available_tools=project.available_tools
        )
        return {"status": "success", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Plugin Upload Endpoint ---
from fastapi import File, UploadFile
import shutil
import re

@app.post("/api/plugins/upload")
async def upload_plugin(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    # Use the relative path of the first file to determine the folder name
    first_file_path = Path(files[0].filename)
    plugin_name = first_file_path.parts[0]

    # 1. Validate plugin name
    if not re.match(r"^[a-zA-Z0-9-]+$", plugin_name):
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid plugin name '{plugin_name}'. Only letters, numbers, and hyphens are allowed."
        )

    plugin_dir = PLUGIN_COLLECTION_DIR / plugin_name
    if plugin_dir.exists():
        raise HTTPException(
            status_code=409, 
            detail=f"Plugin '{plugin_name}' already exists. Please delete the existing folder first."
        )

    # Create a temporary directory to store uploaded files
    temp_dir = Path("temp_plugin_upload")
    temp_dir.mkdir(exist_ok=True)
    temp_plugin_path = temp_dir / plugin_name
    temp_plugin_path.mkdir(exist_ok=True)

    has_init_yaml = False

    try:
        # Save all files to the temporary directory
        for file in files:
            file_path = Path(file.filename)
            # The full path inside the temp dir
            save_path = temp_dir / file_path
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            with save_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # 2. Check for init.yaml in the root of the plugin folder
            if file_path.name == "init.yaml" and len(file_path.parts) == 2:
                has_init_yaml = True

        # 3. Perform validation
        if not has_init_yaml:
            raise HTTPException(
                status_code=400, 
                detail="The plugin must contain an 'init.yaml' file in its root directory."
            )

        # If validation passes, move the folder to the final destination
        shutil.move(str(temp_plugin_path), str(PLUGIN_COLLECTION_DIR))

        # Re-register the new plugin
        try:
            register_plugin(plugin_name)
        except Exception as e:
            # If registration fails, it's not a critical error for the upload itself
            print(f"Warning: Plugin '{plugin_name}' uploaded but failed to register: {e}")

        return {"status": "success", "message": f"Plugin '{plugin_name}' installed successfully."}

    except HTTPException as e:
        # Re-raise HTTP exceptions from our validation
        raise e
    except Exception as e:
        # Catch other potential errors
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
    finally:
        # Clean up the temporary directory
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


@app.delete("/api/plugins/{plugin_name}")
async def unregister_plugin_endpoint(plugin_name: str):
    # Basic security check for plugin_name to prevent path traversal
    if not re.match(r"^[a-zA-Z0-9-]+$", plugin_name) or ".." in plugin_name:
        raise HTTPException(status_code=400, detail="Invalid plugin name.")

    try:
        from src.plugins.plugin_manager import unregister_plugin
        message = unregister_plugin(plugin_name)
        return {"status": "success", "message": message}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unregister plugin: {e}")

@app.get("/api/tools")
async def get_tools():
    """获取所有分组的工具信息."""
    try:
        config = load_global_tool_yaml()
        tool_groups = []
        for plugin_name, plugin_data in config.items():
            if not isinstance(plugin_data, dict):
                continue

            tools = []
            functions = plugin_data.get('functions', {})
            if isinstance(functions, dict):
                for func_key, func_data in functions.items():
                    if isinstance(func_data, dict) and 'function' in func_data:
                        func_details = func_data['function']
                        tools.append({
                            "name": func_details.get('name', func_key),
                            "description": func_details.get('description', 'No description')
                        })

            tool_groups.append({
                "name": plugin_name,
                "description": plugin_data.get('desc', 'No description'),
                "tools": tools
            })
        return tool_groups
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load tools: {e}")




class TaskCreate(BaseModel):
    title: str
    desc: str
    deliverable: str
    worker: str
    judger: str
    available_tools: List[str]
    prompt: str
    judge_mode: bool = False
    task_histories: str = ""

@app.post("/api/tasks")
async def create_task_endpoint(task: TaskCreate):
    from src.plugins.plugin_collection.manager.manager import add_simple_task
    try:
        msg = add_simple_task(
            title=task.title,
            desc=task.desc,
            deliverable=task.deliverable,
            worker=task.worker,
            judger=task.judger,
            available_tools=task.available_tools,
            prompt=task.prompt,
            judge_mode=task.judge_mode,
            task_histories=task.task_histories
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


# --- Schedule & Alarm (Cron) Endpoints ---

def _load_schedule_paths():
    """Read schedule/cron file paths from config, with sensible defaults."""
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

@app.get("/api/plugins")
async def get_plugins():
    plugin_dir = "src/plugins/plugin_collection"
    plugins = []
    if os.path.exists(plugin_dir):
        for name in os.listdir(plugin_dir):
            if os.path.isdir(os.path.join(plugin_dir, name)):
                # Check if registered
                config = get_plugin_config(name)
                plugins.append({
                    "name": name,
                    "enabled": config is not None,
                    "path": os.path.join(plugin_dir, name)
                })
    return plugins

@app.post("/api/plugins/{name}/toggle")
async def toggle_plugin(name: str):
    config = get_plugin_config(name)
    if config:
        # Currently no unregister_plugin in plugin_manager.py but let's assume it exists or we just don't list it
        # Based on user requirement: "支持调用register_plugin和unregister_plugin函数"
        from src.plugins.plugin_manager import unregister_plugin
        unregister_plugin(name)
        return {"enabled": False}
    else:
        register_plugin(name)
        return {"enabled": True}

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
    import json
    res = list_databases()
    return json.loads(res)["content"]["available_databases"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

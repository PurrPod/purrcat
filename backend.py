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
    
    start_lark_sensor()
    
    # Register plugins
    for tool in ["database", "filesystem", "feishu", "manager", "schedule", "web"]:
        try:
            register_plugin(tool)
        except Exception as e:
            print(f"Error registering plugin {tool}: {e}")
            
    # Set up filesystem
    try:
        config_path = os.path.join("data", "config", "file_config.json")
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
    
    # Start Agent in a separate thread
    global agent
    agent = agent_module.Agent.load_checkpoint()
    asyncio.create_task(asyncio.to_thread(agent.sensor))
    
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

@app.get("/api/projects")
async def get_projects():
    projects = []
    for p in project_module.PROJECT_POOL:
        project_data = p.copy()
        # Add history if instance exists
        instance = project_module.PROJECT_INSTANCES.get(p["id"])
        if instance:
            project_data["history"] = instance.current_history
        projects.append(project_data)
    return projects

PROJECT_LOG_PATH_CACHE: Dict[str, str] = {}

def _resolve_project_log_path(project_id: str) -> Optional[str]:
    cached = PROJECT_LOG_PATH_CACHE.get(project_id)
    if cached:
        return cached

    instance = project_module.PROJECT_INSTANCES.get(project_id)
    if instance:
        log_dir = os.path.join("data", "checkpoints", "project", f"{instance.name}_{instance.creat_time}")
        log_path = os.path.join(log_dir, "log.jsonl")
        PROJECT_LOG_PATH_CACHE[project_id] = log_path
        return log_path

    base_dir = os.path.join("data", "checkpoints", "project")
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

@app.get("/api/tasks")
async def get_tasks():
    tasks = []
    for t in task_module.TASK_POOL:
        task_data = t.copy()
        # Add history if instance exists
        instance = task_module.TASK_INSTANCES.get(t["id"])
        if instance:
            task_data["history"] = instance.current_history
        tasks.append(task_data)
    return tasks

@app.post("/api/tasks/{task_id}/stop")
async def stop_task_endpoint(task_id: str):
    if task_module.kill_task(task_id):
        return {"status": "success"}
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

@app.post("/api/config/{filename}")
async def update_config(filename: str, config: Dict[str, Any]):
    if not filename.endswith(".json"):
        filename += ".json"
    file_path = os.path.join("data", "config", filename)
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

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

from src.plugins.plugin_collection.shell.shell import DockerManager

# Use absolute paths so the backend can find data/ even if started from a different cwd
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PLUGIN_COLLECTION_DIR = Path(os.path.join(BASE_DIR, "src", "plugins", "plugin_collection"))

# Import existing logic
from src.agent import agent as agent_module
from src.models import task as task_module
from src.plugins.plugin_collection.filesystem.filesystem import set_allowed_directories, list_special_directories
from src.utils.config import load_config, get_model_config_json, get_mcp_config_json, get_feishu_config, get_rss_subscriptions, get_web_api_config, reload_config

# 确保task_module中有必要的变量和函数
if not hasattr(task_module, 'TASK_POOL'):
    task_module.TASK_POOL = []

if not hasattr(task_module, 'delete_task'):
    def delete_task(task_id):
        if hasattr(task_module, 'TASK_INSTANCES') and task_id in task_module.TASK_INSTANCES:
            del task_module.TASK_INSTANCES[task_id]
        if hasattr(task_module, 'TASK_POOL'):
            task_module.TASK_POOL = [t for t in task_module.TASK_POOL if t.get('id') != task_id]
        if hasattr(task_module, 'dirty_tasks') and hasattr(task_module, 'task_set_lock'):
            with task_module.task_set_lock:
                if task_id in task_module.dirty_tasks:
                    task_module.dirty_tasks.remove(task_id)
        return True
    task_module.delete_task = delete_task

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

    print("🔄 初始化全局工具注册表...")
    init_tool()

    start_sensors()

    _ensure_tasks_loaded_from_checkpoints()

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





def _ensure_tasks_loaded_from_checkpoints():
    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if not os.path.isdir(base_dir):
        return

    existing_ids = {t.get("id") for t in task_module.TASK_POOL}

    for entry in os.listdir(base_dir):
        checkpoint_path = os.path.join(base_dir, entry, "checkpoint.json")
        checkpoint_dir = os.path.dirname(checkpoint_path)
        if not os.path.isfile(checkpoint_path):
            continue
        try:
            task = task_module.Task.load_checkpoint(checkpoint_dir)
            if task and task.task_id not in existing_ids:
                pass
        except Exception:
            pass





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


LOG_READ_LOCK = threading.Lock()
TASK_LOG_READ_CACHE: Dict[str, Dict[str, Any]] = {}








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
    skills: list = None
    core: str = "[1]openai:deepseek-chat"


@app.post("/api/tasks")
async def create_task_endpoint(task: TaskCreate):
    from src.plugins.route.agent_tool import add_task
    try:
        msg = add_task(
            name=task.title,
            prompt=task.prompt,
            core=task.core
        )
        return {"status": "success", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config")
async def get_config():
    """获取配置 - 优先从 config.yaml 读取，兼容旧版 JSON 配置"""
    configs = {}
    
    # 从 config.yaml 读取主要配置
    try:
        # model_config.json 格式（兼容旧代码）
        configs['model_config.json'] = get_model_config_json()
        # mcp_config.json 格式
        configs['mcp_config.json'] = get_mcp_config_json()
        # feishu_config.json 格式
        feishu = get_feishu_config()
        configs['feishu_config.json'] = {
            "APP_ID": feishu.get("app_id", ""),
            "APP_SECRET": feishu.get("app_secret", ""),
            "CHAT_ID": feishu.get("chat_id", "")
        }
        # rss_config.json 格式
        rss_list = get_rss_subscriptions()
        configs['rss_config.json'] = [{"name": r["name"], "rss_url": r["url"]} for r in rss_list]
        # web_config.json 格式
        web = get_web_api_config()
        configs['web_config.json'] = {"TAVILY_API_KEY": web.get("tavily_api_key", "")}
    except Exception as e:
        print(f"[Config] 从 config.yaml 读取配置失败: {e}")
        # 回退到读取 JSON 文件
        config_dir = "data/config"
        if os.path.exists(config_dir):
            for filename in os.listdir(config_dir):
                if filename.endswith(".json"):
                    with open(os.path.join(config_dir, filename), "r", encoding="utf-8") as f:
                        configs[filename] = json.load(f)
    
    return configs


def _load_schedule_paths():
    """加载调度文件路径 - 使用固定路径"""
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
    """更新配置 - 同时更新 config.yaml 和对应的 JSON 文件（兼容旧代码）"""
    if not filename.endswith(".json"):
        filename += ".json"
    
    # 同时写入 JSON 文件（兼容旧代码）
    file_path = os.path.join(DATA_DIR, "config", filename)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    
    # 尝试更新 config.yaml
    try:
        yaml_config = load_config()
        
        if filename == "model_config.json":
            # 更新模型配置
            if "models" in config:
                yaml_config["models"] = config["models"]
            if "agent" in config:
                yaml_config["agent_model"] = config["agent"]
            # 更新专用模型
            for key in ["image_generator", "image_converter", "video_generator", 
                       "audio_generator", "audio_converter", "video_converter"]:
                if key in config:
                    yaml_config.setdefault("specialized_models", {})[key] = config[key]
            if "embedding_model" in config:
                yaml_config["embedding_model"] = config["embedding_model"]
                
        elif filename == "feishu_config.json":
            yaml_config["feishu"] = {
                "app_id": config.get("APP_ID", ""),
                "app_secret": config.get("APP_SECRET", ""),
                "chat_id": config.get("CHAT_ID", "")
            }
            
        elif filename == "mcp_config.json":
            yaml_config["mcp_servers"] = config.get("mcpServers", {})
            
        elif filename == "rss_config.json":
            yaml_config["rss_subscriptions"] = [
                {"name": item["name"], "url": item["rss_url"]} 
                for item in config
            ]
            
        elif filename == "web_config.json":
            yaml_config["web_api"] = {"tavily_api_key": config.get("TAVILY_API_KEY", "")}
        
        # 写回 config.yaml
        yaml_path = os.path.join(DATA_DIR, "config", "config.yaml")
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(yaml_config, f, allow_unicode=True, sort_keys=False)
        
        # 清除配置缓存
        reload_config()
        
    except Exception as e:
        print(f"[Config] 更新 config.yaml 失败: {e}")
        # 继续返回成功，因为 JSON 文件已更新
    
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
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning")
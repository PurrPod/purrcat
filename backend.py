import datetime
import uuid
import socket
import warnings

# 抑制无关警告
warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine 'ExpiringCache._start_clear_cron' was never awaited")
warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated as an API")

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
from src.utils.config import load_config, get_model_config_json, get_mcp_config_json, get_feishu_config, \
    get_rss_subscriptions, get_web_api_config, reload_config, save_config

# ====== 拥抱新架构：引入新版工具管理器 ======
from src.plugins.plugin_manager import init_tool, TOOL_INDEX_FILE, BASE_TOOLS
from src.plugins.plugin_collection.local_manager import register_plugin, unregister_plugin

from src.sensor.const import start_sensors
from src.sensor.feishu import start_lark_sensor


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    os.environ.pop("http_proxy", None)
    os.environ.pop("https_proxy", None)

    print("🔄 初始化配置文件...")
    from src.utils.config import initialize_config
    initialize_config()

    print("🔄 初始化全局工具注册表...")
    init_tool()
    start_sensors()

    global agent
    agent = agent_module.Agent.load_checkpoint()
    agent_sensor_task = asyncio.create_task(asyncio.to_thread(agent.sensor))

    start_lark_sensor(agent)
    yield

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

BACKEND_SERVICE_ID = "cat-in-cup-backend-v1"

@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Agent Backend API is running",
        "service_id": BACKEND_SERVICE_ID
    }


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


@app.get("/api/agent/status")
async def get_agent_status():
    return {
        "window_token": agent.window_token,
        "history_length": len(agent.current_history),
        "state": agent.state
    }


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


class UpdateSystemPromptRequest(BaseModel):
    content: str


@app.post("/api/agent/update-system-prompt")
async def update_system_prompt(request: UpdateSystemPromptRequest):
    """更新Agent的系统提示词并更新历史记录"""
    try:
        # 更新SOUL.md文件
        soul_path = "src/agent/SOUL.md"
        os.makedirs(os.path.dirname(soul_path), exist_ok=True)
        with open(soul_path, "w", encoding="utf-8") as f:
            f.write(request.content)
        
        # 更新agent的系统提示词和历史记录
        agent.system_prompt = request.content
        if agent.current_history and agent.current_history[0].get("role") == "system":
            agent.current_history[0]["content"] = request.content
        else:
            # 如果历史记录中没有系统提示词，添加一个
            agent.current_history.insert(0, {"role": "system", "content": request.content})
        
        # 保存检查点
        agent.save_checkpoint()
        
        return {
            "status": "success",
            "message": "Agent系统提示词已更新并应用",
            "content": request.content
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class UpdateAgentModelRequest(BaseModel):
    model: str


@app.post("/api/agent/model")
async def update_agent_model(request: UpdateAgentModelRequest):
    """更新 Agent 使用的模型"""
    try:
        config = load_config()
        config["agent_model"] = request.model
        save_config(config)
        
        # 这里可以选择重新加载 agent（如果需要）
        # 当前不需要重新加载，下次请求时会自动使用新模型
        
        return {
            "status": "success",
            "message": f"Agent model updated to {request.model}",
            "model": request.model
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/agent/model")
async def get_agent_model():
    """获取当前 Agent 模型"""
    try:
        config = load_config()
        return {
            "model": config.get("agent_model", ""),
            "available_models": list(config.get("models", {}).keys())
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/tasks")
async def get_tasks():
    tasks = []
    for task_id, task in task_module.TASK_INSTANCES.items():
        logs = []
        try:
            log_path = os.path.join(task.checkpoint_dir, "log.jsonl")
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            log_entry = json.loads(line)
                            logs.append(log_entry.get("content", ""))
        except:
            pass

        try:
            created_iso = datetime.datetime.strptime(task.create_time, "%Y%m%d%H%M%S").isoformat()
        except:
            created_iso = datetime.datetime.now().isoformat()

        tasks.append({
            "id": task.task_id,
            "name": task.task_name,
            "state": task.state,
            "status": task.state,
            "progress": 100 if task.state == "completed" else (0 if task.state == "ready" else 50),
            "creat_time": task.create_time,
            "logs": logs[-20:] if logs else [],
            "history": task.history[-10:] if task.history else [],
            "step": task.step,
            "token_usage": task.token_usage,
            "checkpoint_dir": task.checkpoint_dir,
            "createdAt": created_iso,
            "updatedAt": created_iso
        })

    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if os.path.isdir(base_dir):
        for entry in os.listdir(base_dir):
            log_path = os.path.join(base_dir, entry, "log.jsonl")
            if not os.path.exists(log_path):
                continue

            task_id = None
            task_name = entry
            create_time = ""
            logs = []

            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            log_entry = json.loads(line)
                            if not task_id:
                                task_id = log_entry.get("task_id")
                            logs.append(log_entry.get("content", ""))
            except:
                continue

            if task_id and task_id in task_module.TASK_INSTANCES:
                continue

            if "_" in entry:
                parts = entry.split("_")
                create_time = parts[-1]
                task_name = "_".join(parts[:-1])

            try:
                created_iso = datetime.datetime.strptime(create_time, "%Y%m%d%H%M%S").isoformat()
            except:
                created_iso = datetime.datetime.now().isoformat()

            if task_id:
                tasks.append({
                    "id": task_id,
                    "name": task_name,
                    "state": "completed",
                    "status": "completed",
                    "progress": 100,
                    "creat_time": create_time,
                    "logs": logs[-20:] if logs else [],
                    "history": [],
                    "step": 0,
                    "token_usage": 0,
                    "checkpoint_dir": os.path.join(base_dir, entry),
                    "createdAt": created_iso,
                    "updatedAt": created_iso
                })

    return tasks


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
        log_dir = os.path.join(DATA_DIR, "checkpoints", "task", f"{instance.task_name}_{instance.create_time}")
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


@app.post("/api/tasks/{task_id}/stop")
async def stop_task_endpoint(task_id: str):
    task_module.kill_task(task_id)
    return {"status": "success"}


@app.delete("/api/tasks/{task_id}")
async def remove_task_endpoint(task_id: str):
    task_module.kill_task(task_id)
    if task_id in task_module.TASK_INSTANCES:
        del task_module.TASK_INSTANCES[task_id]

    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    dirs_to_delete = []

    if os.path.isdir(base_dir):
        for entry in os.listdir(base_dir):
            log_path = os.path.join(base_dir, entry, "log.jsonl")
            if os.path.exists(log_path):
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                log_entry = json.loads(line)
                                if log_entry.get("task_id") == task_id:
                                    dirs_to_delete.append(os.path.join(base_dir, entry))
                                    break
                except:
                    pass

    for dir_path in dirs_to_delete:
        try:
            shutil.rmtree(dir_path)
        except:
            pass

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
        init_tool()
        return {"status": "success", "message": "Plugin unregistered successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unregister plugin: {e}")


@app.get("/api/tools")
async def get_tools():
    try:
        tools_list = []
        if os.path.exists(TOOL_INDEX_FILE):
            with open(TOOL_INDEX_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        tools_list.append(json.loads(line))

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
                "description": t["desc"],
                "parameters": t.get("parameters", {})
            })

        base_plugin = {
            "name": "system_core",
            "description": "[CORE] 系统核心指令",
            "tools": []
        }
        for bt in BASE_TOOLS:
            base_plugin["tools"].append({
                "name": bt["function"]["name"],
                "description": bt["function"]["description"],
                "parameters": bt["function"].get("parameters", {})
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
                plugin_info = {
                    "name": name,
                    "enabled": name in active_plugins,
                    "path": full_path,
                    "config": {},
                    "description": ""
                }
                yaml_path = os.path.join(full_path, f"{name}.yaml")
                if not os.path.exists(yaml_path):
                    yaml_path = os.path.join(full_path, "init.yaml")

                if os.path.exists(yaml_path):
                    try:
                        with open(yaml_path, "r", encoding="utf-8") as f:
                            config_data = yaml.safe_load(f) or {}
                            plugin_info["config"] = config_data
                            # 尝试从多个地方获取描述
                            # 1. 直接在根目录下查找 description 或 desc
                            if "description" in config_data:
                                plugin_info["description"] = config_data["description"]
                            elif "desc" in config_data:
                                plugin_info["description"] = config_data["desc"]
                            # 2. 查找插件名称对应的顶层键，然后在其下查找 desc
                            elif name in config_data:
                                plugin_config = config_data[name]
                                if isinstance(plugin_config, dict):
                                    if "description" in plugin_config:
                                        plugin_info["description"] = plugin_config["description"]
                                    elif "desc" in plugin_config:
                                        plugin_info["description"] = plugin_config["desc"]
                                    # 3. 尝试从 functions 中提取描述
                                    elif "functions" in plugin_config and plugin_config["functions"]:
                                        for func_name, func_info in plugin_config["functions"].items():
                                            if isinstance(func_info, dict):
                                                # 处理嵌套的 function 结构
                                                if "function" in func_info and isinstance(func_info["function"],
                                                                                          dict) and "description" in \
                                                        func_info["function"]:
                                                    plugin_info["description"] = func_info["function"]["description"]
                                                    break
                                                elif "description" in func_info:
                                                    plugin_info["description"] = func_info["description"]
                                                    break
                            # 4. 直接从根目录的 functions 中提取描述
                            elif "functions" in config_data and config_data["functions"]:
                                for func_name, func_info in config_data["functions"].items():
                                    if isinstance(func_info, dict):
                                        # 处理嵌套的 function 结构
                                        if "function" in func_info and isinstance(func_info["function"],
                                                                                  dict) and "description" in func_info[
                                            "function"]:
                                            plugin_info["description"] = func_info["function"]["description"]
                                            break
                                        elif "description" in func_info:
                                            plugin_info["description"] = func_info["description"]
                                            break
                    except Exception:
                        pass
                plugins.append(plugin_info)
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
        init_tool()
        return {"enabled": False}
    else:
        register_plugin(name)
        init_tool()
        return {"enabled": True}


class TaskCreate(BaseModel):
    title: str
    desc: str
    deliverable: str
    prompt: str
    skills: list = None
    core: str = "openai:deepseek-chat"
    judger: str = "openai:deepseek-chat"


@app.post("/api/tasks")
async def create_task_endpoint(task: TaskCreate):
    from src.plugins.route.agent_tool import add_task
    try:
        msg = add_task(
            name=task.title,
            prompt=task.prompt,
            core=task.core,
            judger=task.judger
        )
        return {"status": "success", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config")
async def get_config():
    configs = {}
    try:
        configs['model_config.json'] = get_model_config_json()
        configs['mcp_config.json'] = get_mcp_config_json()

        # 直接从 secrets 目录读取飞书配置
        feishu_yaml_path = os.path.join(DATA_DIR, "config", "secrets", "feishu.yaml")
        if os.path.exists(feishu_yaml_path):
            with open(feishu_yaml_path, "r", encoding="utf-8") as f:
                feishu_yaml = yaml.safe_load(f)
            configs['channel_config.json'] = {
                "feishu": {
                    "app_id": feishu_yaml.get("feishu", {}).get("app_id", ""),
                    "app_secret": feishu_yaml.get("feishu", {}).get("app_secret", ""),
                    "chat_id": feishu_yaml.get("feishu", {}).get("chat_id", "")
                },
                "other": []
            }
        else:
            configs['channel_config.json'] = {
                "feishu": {
                    "app_id": "",
                    "app_secret": ""
                },
                "other": []
            }
        
        # 直接从 secrets 目录读取 web_api 配置
        web_api_yaml_path = os.path.join(DATA_DIR, "config", "secrets", "web_api.yaml")
        if os.path.exists(web_api_yaml_path):
            with open(web_api_yaml_path, "r", encoding="utf-8") as f:
                web_api_yaml = yaml.safe_load(f)
            configs['tool_config.json'] = {
                "web_api": {
                    "tavily_api_key": web_api_yaml.get("web_api", {}).get("tavily_api_key", "")
                }
            }
        else:
            configs['tool_config.json'] = {
                "web_api": {
                    "tavily_api_key": ""
                }
            }
        
        # 直接读取 file_config.json 文件
        file_config_path = os.path.join(DATA_DIR, "config", "file_config.json")
        if os.path.exists(file_config_path):
            with open(file_config_path, "r", encoding="utf-8") as f:
                file_config = json.load(f)
            configs['permission_config.json'] = file_config
        else:
            configs['permission_config.json'] = {
                "sandbox_dirs": ["sandbox/", "agent_vm/"],
                "skill_dir": ["data/skill"],
                "dont_read_dirs": ["src/"]
            }

        rss_list = get_rss_subscriptions()
        configs['rss_config.json'] = [{"name": r["name"], "rss_url": r["url"]} for r in rss_list]
    except Exception as e:
        print(f"Error in get_config: {e}")

    return configs


def _load_schedule_paths():
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

    # 将属于 YAML 的配置拦截，不生成根目录的无用 JSON；而 file_config.json 将在这里正常存储
    yaml_mapped_files = ["feishu_config.json", "web_api_config.json", "model_config.json", "mcp_config.json",
                         "rss_config.json"]
    if filename not in yaml_mapped_files:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

    try:
        yaml_config = load_config()
        if filename == "model_config.json":
            if "models" in config:
                # 保留 api_keys 数组，因为后端支持多个 API-key 轮询
                models = config["models"]
                for model_name, model_config in models.items():
                    # 确保 api_keys 是数组格式
                    if "api_keys" in model_config and not isinstance(model_config["api_keys"], list):
                        model_config["api_keys"] = [model_config["api_keys"]]
                    # 如果 api_keys 为空数组，删除它
                    elif "api_keys" in model_config and not model_config["api_keys"]:
                        del model_config["api_keys"]
                yaml_config["models"] = models
            if "agent" in config:
                yaml_config["agent_model"] = config["agent"]
            for key in ["image_generator", "image_converter", "video_generator",
                        "audio_generator", "audio_converter", "video_converter"]:
                if key in config:
                    yaml_config.setdefault("specialized_models", {})[key] = config[key]
            if "embedding_model" in config:
                yaml_config["embedding_model"] = config["embedding_model"]
            
            # --- 持久化写入到 secrets/models.yaml --- 
            models_data = {}
            if "models" in yaml_config:
                models_data["models"] = yaml_config["models"]
            if "specialized_models" in yaml_config:
                models_data["specialized_models"] = yaml_config["specialized_models"]
            
            models_yaml_path = os.path.join(DATA_DIR, "config", "secrets", "models.yaml")
            os.makedirs(os.path.dirname(models_yaml_path), exist_ok=True)
            with open(models_yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(models_data, f, allow_unicode=True, sort_keys=False)

        elif filename == "feishu_config.json":
            feishu_data = config.get("feishu", {})
            yaml_config["feishu"] = feishu_data

            # --- 持久化写入到 secrets/feishu.yaml ---
            feishu_yaml_path = os.path.join(DATA_DIR, "config", "secrets", "feishu.yaml")
            os.makedirs(os.path.dirname(feishu_yaml_path), exist_ok=True)
            with open(feishu_yaml_path, "w", encoding="utf-8") as f:
                yaml.dump({"feishu": feishu_data}, f, allow_unicode=True, sort_keys=False)

        elif filename == "web_api_config.json":
            web_api_data = config.get("web_api", {})
            yaml_config["web_api"] = web_api_data

            # --- 持久化写入到 secrets/web_api.yaml ---
            web_yaml_path = os.path.join(DATA_DIR, "config", "secrets", "web_api.yaml")
            os.makedirs(os.path.dirname(web_yaml_path), exist_ok=True)
            with open(web_yaml_path, "w", encoding="utf-8") as f:
                yaml.dump({"web_api": web_api_data}, f, allow_unicode=True, sort_keys=False)
                
        elif filename == "channel_config.json":
            # 处理频道配置
            if "feishu" in config:
                feishu_data = config["feishu"]
                yaml_config["feishu"] = {
                    "app_id": feishu_data.get("app_id", ""),
                    "app_secret": feishu_data.get("app_secret", ""),
                    "chat_id": feishu_data.get("chat_id", "")
                }
                
                # 持久化写入到 secrets/feishu.yaml
                feishu_yaml_path = os.path.join(DATA_DIR, "config", "secrets", "feishu.yaml")
                os.makedirs(os.path.dirname(feishu_yaml_path), exist_ok=True)
                with open(feishu_yaml_path, "w", encoding="utf-8") as f:
                    yaml.dump({"feishu": yaml_config["feishu"]}, f, allow_unicode=True, sort_keys=False)
                    
        elif filename == "tool_config.json":
            # 处理工具配置
            if "web_api" in config:
                web_api_data = config["web_api"]
                yaml_config["web_api"] = {
                    "tavily_api_key": web_api_data.get("tavily_api_key", "")
                }
                
                # 持久化写入到 secrets/web_api.yaml
                web_yaml_path = os.path.join(DATA_DIR, "config", "secrets", "web_api.yaml")
                os.makedirs(os.path.dirname(web_yaml_path), exist_ok=True)
                with open(web_yaml_path, "w", encoding="utf-8") as f:
                    yaml.dump({"web_api": yaml_config["web_api"]}, f, allow_unicode=True, sort_keys=False)
                    
        elif filename == "permission_config.json":
            # 处理权限设置
            # 直接保存到 file_config.json 文件
            file_config_path = os.path.join(DATA_DIR, "config", "file_config.json")
            
            # 保存到 file_config.json 文件
            with open(file_config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

        elif filename == "mcp_config.json":
            yaml_config["mcp_servers"] = config.get("mcpServers", {})

            mcp_yaml_path = os.path.join(DATA_DIR, "config", "configs", "mcp_servers.yaml")
            os.makedirs(os.path.dirname(mcp_yaml_path), exist_ok=True)
            with open(mcp_yaml_path, "w", encoding="utf-8") as f:
                yaml.dump({"mcp_servers": yaml_config["mcp_servers"]}, f, allow_unicode=True, sort_keys=False)

        elif filename == "rss_config.json":
            yaml_config["rss_subscriptions"] = [
                {"name": item["name"], "url": item["rss_url"]}
                for item in config
            ]
            rss_yaml_path = os.path.join(DATA_DIR, "config", "configs", "rss_subscriptions.yaml")
            os.makedirs(os.path.dirname(rss_yaml_path), exist_ok=True)
            with open(rss_yaml_path, "w", encoding="utf-8") as f:
                yaml.dump({"rss_subscriptions": yaml_config["rss_subscriptions"]}, f, allow_unicode=True,
                          sort_keys=False)

        # 更新整合的全局 config.yaml (这由 initialize_config() 热加载依赖)
        yaml_path = os.path.join(DATA_DIR, "config", "config.yaml")
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(yaml_config, f, allow_unicode=True, sort_keys=False)

        reload_config()
    except Exception as e:
        print(f"Update Config Error: {e}")
        pass

    return {"status": "success"}


@app.get("/api/skills")
async def get_skills():
    skill_dir = os.path.join(DATA_DIR, "skill")
    skills = []
    if os.path.exists(skill_dir):
        for name in os.listdir(skill_dir):
            if os.path.isdir(os.path.join(skill_dir, name)):
                desc = ""
                skill_md_path = os.path.join(skill_dir, name, "SKILL.md")
                if os.path.exists(skill_md_path):
                    try:
                        with open(skill_md_path, "r", encoding="utf-8") as f:
                            desc = f.read()
                    except Exception:
                        pass
                skills.append({
                    "name": name,
                    "path": os.path.join(skill_dir, name),
                    "description": desc
                })
    return skills


@app.post("/api/skills/upload")
async def upload_skill(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    first_file_path = Path(files[0].filename)
    skill_name = first_file_path.parts[0]
    skill_dir = os.path.join(DATA_DIR, "skill", skill_name)
    os.makedirs(skill_dir, exist_ok=True)

    try:
        for file in files:
            file_path = Path(file.filename)
            save_path = os.path.join(DATA_DIR, "skill", str(file_path))
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        return {"status": "success", "message": f"Skill '{skill_name}' uploaded successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/skills/{skill_name}")
async def delete_skill(skill_name: str):
    skill_dir = os.path.join(DATA_DIR, "skill", skill_name)
    if os.path.exists(skill_dir):
        shutil.rmtree(skill_dir)
        return {"status": "success", "message": f"Skill '{skill_name}' deleted."}
    raise HTTPException(status_code=404, detail="Skill not found")


import subprocess

@app.get("/api/sandbox/status")
async def get_sandbox_status():
    try:
        # 检查 Docker 是否在运行
        result = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            return {"running": True, "status": "running"}
        else:
            return {"running": False, "status": "stopped"}
    except Exception as e:
        return {"running": False, "status": "error", "message": str(e)}


@app.get("/api/databases")
async def get_databases():
    from src.plugins.plugin_collection.database.database import list_databases
    res = list_databases()
    return json.loads(res)["content"]["available_databases"]


@app.get("/api/sandbox/status")
async def get_sandbox_status():
    try:
        from src.plugins.plugin_collection.shell.shell import _docker_manager_instance
        if _docker_manager_instance and _docker_manager_instance.container:
            _docker_manager_instance.container.reload()
            running = _docker_manager_instance.container.status == "running"
            return {"running": running, "status": _docker_manager_instance.container.status}
        return {"running": False, "status": "not_initialized"}
    except Exception as e:
        return {"running": False, "status": "error", "error": str(e)}


def is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """检查端口是否可用"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def find_available_port(start_port: int, max_attempts: int = 100, host: str = "0.0.0.0") -> int:
    """从指定端口开始寻找可用端口"""
    for port in range(start_port, start_port + max_attempts):
        if is_port_available(port, host):
            return port
    raise RuntimeError(f"无法找到可用端口 (尝试范围: {start_port}-{start_port + max_attempts - 1})")


def write_port_file(port: int):
    """将实际使用的端口写入文件，供前端读取"""
    port_file = os.path.join(BASE_DIR, "data", "backend_port.json")
    os.makedirs(os.path.dirname(port_file), exist_ok=True)
    with open(port_file, "w", encoding="utf-8") as f:
        json.dump({
            "port": port,
            "service_id": BACKEND_SERVICE_ID,
            "timestamp": datetime.datetime.now().isoformat()
        }, f)


if __name__ == "__main__":
    import uvicorn
    import logging
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    if not os.path.exists(os.path.join(BASE_DIR, "agent_vm")):
        os.mkdir(os.path.join(BASE_DIR, "agent_vm"))
    DEFAULT_PORT = 8001
    try:
        port = find_available_port(DEFAULT_PORT)
        if port != DEFAULT_PORT:
            print(f"⚠️ 端口 {DEFAULT_PORT} 已被占用，自动切换到端口 {port}")
        write_port_file(port)
        print(f"🚀 后端服务启动于 http://0.0.0.0:{port}")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
    except RuntimeError as e:
        print(f"❌ 启动失败: {e}")
        raise
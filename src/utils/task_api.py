import os
import json
from src.harness.process import TASK_INSTANCES, reload_task_by_id, kill_task as process_kill_task, kill_and_cleanup_task
from src.utils.config import DATA_DIR


def get_task_list():
    tasks = []
    for task_id, task in TASK_INSTANCES.items():
        tasks.append({
            "id": task.task_id,
            "name": task.task_name,
            "graph_name": getattr(task, 'graph_name', 'default'),
            "state": task.state,
            "step": getattr(task, 'step', 0),
            "expert_type": task.__class__.__name__,
            "create_time": task.create_time,
            "token_usage": getattr(task, 'token_usage', 0),
            "checkpoint_dir": getattr(task, 'checkpoint_dir', "")
        })
    return tasks


def get_task_log_jsonl(task_id: str):
    task = TASK_INSTANCES.get(task_id) or reload_task_by_id(task_id)
    if not task:
        return None

    log_file = os.path.join(task.checkpoint_dir, "log.jsonl")
    if not os.path.exists(log_file):
        return []

    logs = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return logs


def get_task_state(task_id: str):
    task = TASK_INSTANCES.get(task_id) or reload_task_by_id(task_id)
    if not task:
        return None

    return {
        "task_id": task.task_id,
        "state": task.state,
        "graph": task.graph,
        "node_states": task.node_state,
        "outputs": task.outputs
    }


def kill_task(task_id: str):
    success = process_kill_task(task_id)
    return success


def submit_instruction(task_id: str, node_id: str, content: str):
    task = TASK_INSTANCES.get(task_id) or reload_task_by_id(task_id)
    if not task:
        return None, "Task not found"

    if node_id not in task.node_list:
        return None, f"Node '{node_id}' not found in task '{task_id}'"

    task.submit_request(node_id, content)
    return {"status": "ok", "message": f"Instruction submitted to node {node_id}"}, None


def delete_task(task_id: str):
    success = kill_and_cleanup_task(task_id)
    return success


def get_task_history(task_id: str):
    from src.harness import process as task_module

    task_instance = task_module.TASK_INSTANCES.get(task_id)
    if task_instance:
        return task_instance.history

    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if os.path.isdir(base_dir):
        for entry in os.listdir(base_dir):
            if task_id in entry or entry == task_id:
                history_path = os.path.join(base_dir, entry, "history.json")
                if os.path.exists(history_path):
                    with open(history_path, "r", encoding="utf-8") as f:
                        return json.load(f)
    return []


def force_push_task(task_id: str, content: str):
    from src.harness import process as task_module
    success = task_module.inject_task_instruction(task_id, content)
    return success


def get_task_window_token(task_id: str):
    task_instance = TASK_INSTANCES.get(task_id)
    if task_instance and hasattr(task_instance, 'window_token'):
        return task_instance.window_token

    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if os.path.isdir(base_dir):
        for task_dir in os.listdir(base_dir):
            checkpoint_path = os.path.join(base_dir, task_dir, "checkpoint.json")
            if os.path.exists(checkpoint_path):
                try:
                    with open(checkpoint_path, "r", encoding="utf-8") as f:
                        state = json.load(f)
                        if state.get("task_id") == task_id:
                            return state.get("window_token", 0)
                except Exception:
                    continue
    return 0


def get_task_max_token():
    return 120000

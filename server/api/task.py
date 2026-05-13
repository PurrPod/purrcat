import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.utils.task_api import (
    get_task_list, get_task_state, kill_task, submit_instruction, delete_task
)
from src.utils.log_api import format_task_log
from src.utils.task_api import get_task_log_jsonl

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])

class SubmitInstructionRequest(BaseModel):
    node_id: str
    content: str


@router.get("")
def list_tasks():
    return get_task_list()


@router.get("/{task_id}/log")
def get_task_log(task_id: str):
    log_content = format_task_log(task_id)
    return {
        "task_id": task_id,
        "log": log_content
    }


@router.get("/{task_id}/log/jsonl")
def get_task_log_jsonl_api(task_id: str):
    logs = get_task_log_jsonl(task_id)
    if logs is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return logs


@router.get("/{task_id}/state")
def get_task_state_api(task_id: str):
    result = get_task_state(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.post("/{task_id}/kill")
def kill_task_api(task_id: str):
    success = kill_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or already killed")
    return {"status": "ok", "message": f"Task {task_id} successfully killed."}


@router.post("/{task_id}/submit")
def submit_instruction_api(task_id: str, req: SubmitInstructionRequest):
    result, error = submit_instruction(task_id, req.node_id, req.content)
    if error:
        if "not found" in error.lower():
            raise HTTPException(status_code=404, detail=error)
        raise HTTPException(status_code=400, detail=error)
    return result


@router.delete("/{task_id}")
def delete_task_api(task_id: str):
    success = delete_task(task_id)
    if success:
        return {"status": "ok", "message": f"Task {task_id} successfully deleted."}
    raise HTTPException(status_code=404, detail="Task not found")

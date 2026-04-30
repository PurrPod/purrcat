"""Task 操作模块 - 任务创建、通知和终止"""

import os
import json
import threading
from typing import Dict

from src.utils.config import get_model_config


def add_task_operation(name: str, prompt: str, expert: str,
                       core: str = "openai:deepseek-v4-flash",
                       expert_kwargs: dict = None) -> tuple:
    """
    创建后台任务

    Args:
        name: 任务名称
        prompt: 任务提示
        expert: 专家类型
        core: 使用的模型/工人代号
        expert_kwargs: 专家额外参数

    Returns:
        (result_dict, error_message)
    """
    try:
        # 验证模型配置
        model_name = core
        models = get_model_config().get("main", {})
        if model_name not in models:
            return None, f"未找到模型 '{model_name}' 的配置"

        model_info = models[model_name]
        api_keys = model_info.get("api_keys") or [model_info.get("api_key")]
        valid_api_keys = [key for key in api_keys if key and key.strip()]

        if not valid_api_keys:
            return None, f"模型 '{model_name}' 未配置有效的 api-key"

        expert_kwargs = expert_kwargs or {}
        
        # 创建任务
        from src.harness.task_factory import TaskFactory
        single_task = TaskFactory.create_task(
            expert_type=expert,
            task_name=name,
            prompt=prompt,
            core=core,
            **expert_kwargs
        )

        # 后台执行任务
        def _run_task():
            from src.agent.manager import get_agent
            try:
                result = single_task.run()
                task_id = single_task.task_id
                notify_msg = f"任务 '{name}' (ID: {task_id}) 已执行完毕，结果交付如下：\n{result}"
                agent = get_agent()
                if agent:
                    agent.force_push(notify_msg, type="task_message")
            except Exception as e:
                single_task.state = "error"
                error_msg = f"任务 '{name}' (ID: {single_task.task_id}) 执行崩溃，原因：\n {e}"
                agent = get_agent()
                if agent:
                    agent.force_push(error_msg, type="task_message")

        t = threading.Thread(target=_run_task, daemon=True)
        t.start()

        return {
            "task_id": single_task.task_id,
            "name": name,
            "message": f"任务 '{name}' 已提交到后台线程执行。ID: {single_task.task_id}"
        }, None

    except Exception as e:
        return None, f"创建任务失败: {str(e)}"


def inform_task_operation(task_id: str, action: str = "continue") -> tuple:
    """
    与任务交互：追加指令
    
    Args:
        task_id: 任务ID
        action: 要注入的指令
    
    Returns:
        (result_dict, error_message)
    """
    from src.harness.task import BaseTask

    try:
        # 从内存查找任务
        from src.harness.task_store import TASK_INSTANCES
        task = TASK_INSTANCES.get(task_id)

        # 如果内存中没有，尝试从检查点加载
        if not task:
            from src.utils.config import get_data_dir
            checkpoints_dir = os.path.join(get_data_dir(), "checkpoints", "task")
            if os.path.exists(checkpoints_dir):
                for folder in os.listdir(checkpoints_dir):
                    folder_path = os.path.join(checkpoints_dir, folder)
                    ckpt_path = os.path.join(folder_path, "checkpoint.json")
                    if os.path.exists(ckpt_path):
                        try:
                            with open(ckpt_path, "r", encoding="utf-8") as f:
                                state = json.load(f)
                            if state.get("task_id") == task_id:
                                from src.harness.task import auto_discover_experts
                                auto_discover_experts()
                                expert_type = state.get("expert_type", "BaseTask")
                                if expert_type in BaseTask._EXPERT_REGISTRY:
                                    TargetClass = BaseTask._EXPERT_REGISTRY[expert_type]["class"]
                                    task = TargetClass.load_checkpoint(folder_path)
                                else:
                                    task = BaseTask.load_checkpoint(folder_path)
                                break
                        except Exception as e:
                            print(f"尝试加载检查点时发生异常: {e}")
                            pass

        if not task:
            return None, f"未找到ID为 {task_id} 的任务历史。"

        # 注入指令
        new_prompt = action
        if hasattr(task, 'submit_request'):
            task.submit_request(new_prompt)
            return {
                "task_id": task_id,
                "message": f"指令已注入任务 (ID: {task_id})。"
            }, None
        else:
            return None, f"任务不支持指令注入"

    except Exception as e:
        return None, f"注入指令失败: {str(e)}"


def kill_task_operation(task_id: str) -> tuple:
    """
    终止任务
    
    Args:
        task_id: 任务ID
    
    Returns:
        (result_dict, error_message)
    """
    from src.harness.task_killer import core_kill_task

    try:
        is_killed = core_kill_task(task_id)
        if is_killed:
            return {
                "task_id": task_id,
                "message": f"已成功向任务 (ID: {task_id}) 发送终止信号，任务将被安全强杀。"
            }, None
        else:
            return None, f"终止失败：未在内存中找到运行中的任务 (ID: {task_id})。"

    except Exception as e:
        return None, f"终止任务失败: {str(e)}"


def list_tasks_operation() -> tuple:
    """
    列出所有任务
    
    Returns:
        (tasks_list, error_message)
    """
    try:
        from src.harness.task_store import TASK_INSTANCES
        
        tasks = []
        for task_id, task in TASK_INSTANCES.items():
            tasks.append({
                "task_id": task_id,
                "name": getattr(task, 'task_name', '未知'),
                "state": getattr(task, 'state', '未知'),
                "expert_type": getattr(task, 'expert_type', '未知')
            })

        return {
            "tasks": tasks,
            "count": len(tasks)
        }, None

    except Exception as e:
        return None, f"获取任务列表失败: {str(e)}"
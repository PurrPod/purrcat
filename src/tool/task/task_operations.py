"""Task 操作模块 - 任务创建和终止"""

import threading

from src.utils.config import get_model_config


def add_task_operation(name: str, inputs: dict, graph_name: str,
                       core: str = "openai:deepseek-v4-flash") -> tuple:
    """
    创建后台任务

    Args:
        name: 任务名称
        inputs: 任务输入参数字典
        graph_name: 工作流图名称
        core: 使用的模型/工人代号

    Returns:
        (result_dict, error_message)
    """
    try:
        model_name = core
        models = get_model_config().get("main", {})
        if model_name not in models:
            return None, f"未找到模型 '{model_name}' 的配置"

        model_info = models[model_name]
        api_keys = model_info.get("api_keys") or [model_info.get("api_key")]
        valid_api_keys = [key for key in api_keys if key and key.strip()]

        if not valid_api_keys:
            return None, f"模型 '{model_name}' 未配置有效的 api-key"

        from src.harness.process import Task
        single_task = Task(
            task_name=name,
            inputs=inputs,
            core=core,
            graph_name=graph_name
        )

        # 后台执行任务
        def _run_task():
            import asyncio
            from src.agent.manager import get_agent
            try:
                result = asyncio.run(single_task.run())
                task_id = single_task.task_id
                notify_msg = result or f"任务 '{name}' (ID: {task_id}) 已执行完毕。"
                agent = get_agent()
                if agent:
                    agent.force_push(notify_msg, type="task_message")
            except Exception as e:
                error_msg = f"任务 '{name}' (ID: {single_task.task_id}) 执行崩溃，原因：\n {e}"
                agent = get_agent()
                if agent:
                    agent.force_push(error_msg, type="task_message")

        t = threading.Thread(target=_run_task, daemon=True)
        t.start()

        return {
            "task_id": single_task.task_id,
            "name": name,
            "message": f"任务 '{name}' 已提交到后台线程执行，完成或崩溃会通过消息通知您，无须且请勿频繁检查任务状态。ID: {single_task.task_id}"
        }, None

    except Exception as e:
        return None, f"创建任务失败: {str(e)}"


def kill_task_operation(task_id: str) -> tuple:
    """
    终止任务

    Args:
        task_id: 任务ID

    Returns:
        (result_dict, error_message)
    """
    from src.harness.process import kill_task

    try:
        is_killed = kill_task(task_id)
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
    from src.harness.process import TASK_INSTANCES
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


def submit_request_operation(task_id: str, content: str, node_id: str = None) -> tuple:
    """
    向任务注入指令

    Args:
        task_id: 任务ID
        content: 注入的指令内容
        node_id: (可选) 指定的节点ID

    Returns:
        (result_dict, error_message)
    """
    from src.harness.process import inject_task_instruction, TASK_INSTANCES

    if task_id not in TASK_INSTANCES:
        return None, f"注入失败：未在内存中找到运行中的任务 (ID: {task_id})。"

    try:
        success = inject_task_instruction(task_id, content, node_id)
        if success:
            target_info = f"节点 [{node_id}]" if node_id else "所有节点"
            return {
                "task_id": task_id,
                "message": f"已成功向任务 (ID: {task_id}) 的 {target_info} 注入指令。"
            }, None
        else:
            return None, f"向任务 (ID: {task_id}) 注入指令失败，请检查任务状态。"

    except Exception as e:
        return None, f"注入指令发生异常: {str(e)}"
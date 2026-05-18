"""Task 操作模块 - 任务创建、终止、查询及指令注入"""

import threading

def add_task_operation(name: str, inputs: dict, graph_name: str) -> tuple:
    """创建后台任务"""
    try:
        from src.harness.process import Task

        single_task = Task(
            task_name=name, inputs=inputs, graph_name=graph_name
        )
        
        model_name = single_task.core
        from src.utils.config import get_model_config
        models = get_model_config().get("main", {})
        
        if model_name not in models:
            return None, f"任务创建失败：图配置的驱动模型 '{model_name}' 未在系统中找到配置。"

        model_info = models[model_name]
        api_keys = model_info.get("api_keys") or [model_info.get("api_key")]
        valid_api_keys = [key for key in api_keys if key and key.strip()]

        if not valid_api_keys:
            return None, f"任务创建失败：图配置的驱动模型 '{model_name}' 未配置有效的 api-key。"

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
            "message": f"任务 '{name}' (图: {graph_name}) 已提交后台执行。完成或崩溃会发送通知，无须频繁查询状态。ID: {single_task.task_id}",
        }, None

    except Exception as e:
        return None, f"创建任务失败: {str(e)}"


def list_tasks_operation() -> tuple:
    """列出所有任务及详细状态"""
    from src.harness.process import TASK_INSTANCES

    tasks = []
    for task_id, task in TASK_INSTANCES.items():
        state_val = getattr(task, "state", "未知")
        # 兼容 Enum 类型输出
        state_str = state_val.value if hasattr(state_val, "value") else str(state_val)
        
        tasks.append({
            "task_id": task_id,
            "name": getattr(task, "task_name", "未知"),
            "graph_name": getattr(task, "graph_name", "未知"),
            "state": state_str,
            "create_time": getattr(task, "create_time", "未知"),
            "core": getattr(task, "core", "未知")
        })

    return {"tasks": tasks, "count": len(tasks)}, None


def kill_task_operation(task_id: str) -> tuple:
    """终止任务"""
    from src.harness.process import kill_task

    try:
        is_killed = kill_task(task_id)
        if is_killed:
            return {"task_id": task_id, "message": f"已成功向任务 (ID: {task_id}) 发送强杀信号。"}, None
        else:
            return None, f"终止失败：未在内存中找到任务 (ID: {task_id})。"
    except Exception as e:
        return None, f"终止任务失败: {str(e)}"


def submit_request_operation(task_id: str, content: str, node_id: str) -> tuple:
    """向任务的特定节点注入指令，并在需要时安全地重启物理线程"""
    from src.harness.process import TASK_INSTANCES, TaskState

    if not node_id:
        return None, "注入失败：必须明确指定 node_id，不支持全局广播。"

    if task_id not in TASK_INSTANCES:
        return None, f"注入失败：未在内存中找到运行中的任务 (ID: {task_id})。"

    task = TASK_INSTANCES[task_id]

    # 🌟 核心修复：在注入前（此时状态还未被改写），判断守护线程是否已经结束
    need_restart_thread = task.state in [
        TaskState.INTERRUPTED,
        TaskState.ERROR,
        TaskState.COMPLETED
    ]

    try:
        # 拦截：确保目标节点存在
        if node_id not in task.node_list:
             return None, f"注入失败：任务中不存在节点 [{node_id}]"

        # 执行规范化单节点注入
        result = task.inject_instruction(node_id, content)
        success = result.get("status") == "success"

        if success:
            # 🌟 如果原线程已死寂，重新拉起新的物理线程
            if need_restart_thread:
                import asyncio
                
                def _resume_task():
                    try:
                        asyncio.run(task.run())
                    except Exception as e:
                        print(f"恢复任务运行异常: {e}")
                        
                t = threading.Thread(target=_resume_task, daemon=True)
                t.start()

            return {
                "task_id": task_id,
                "message": f"已成功向任务 (ID: {task_id}) 的节点 [{node_id}] 注入指令，工作流已恢复执行。",
            }, None
        else:
            err_msg = result.get("message", "内部错误")
            return None, f"向节点 [{node_id}] 注入指令被拒：{err_msg}"

    except Exception as e:
        return None, f"注入指令发生代码级异常: {str(e)}"
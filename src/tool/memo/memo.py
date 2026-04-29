"""Memo 工具主入口 - 更新系统备忘录"""

import traceback
from src.tool.utils.format import text_response, error_response, warning_response
from src.tool.memo.memo_operations import (
    _validate_params,
    _update_core_information,
    _push_to_purrmemo,
    build_flush_data
)


def Memo(short_term: str = None, events: list = None, work_exp: list = None, 
         cognition: list = None, reminders: str = None, project_state: str = None) -> str:
    """
    更新系统备忘录，并异步触发核心档案更新
    
    Args:
        short_term: 短期工作状态：当前处理的任务细节、挂起步骤、临时变量等即时上下文（必填）
        events: 事件记录：每条包含 time（格式YYYYMMDDHHMM）和 event 描述。记录发生过的事实、对话、操作
        work_exp: 经验增长：每条一句简短经验。用户偏好、避坑教训、有效工作模式等可复用的沉淀
        cognition: 认知记录：每条一句简短认知，包含事物本身及其联系
        reminders: 待办提醒：需要后续跟进的未完成任务、待处理事项
        project_state: 项目状态：当前项目的整体进度、关键上下文、已完成和待完成的工作
    
    Returns:
        格式化后的 JSON 字符串，包含 timestamp, type, content, snip
    """
    try:
        # 参数校验：先进行类型校验，防止大模型传入错误类型
        for param_name, param_val in [("events", events), ("work_exp", work_exp), ("cognition", cognition)]:
            if param_val is not None and not isinstance(param_val, list):
                return error_response(f"参数类型错误: {param_name} 必须是 JSON 数组 (List) 格式，你传入了 {type(param_val).__name__}。请修改参数格式后重试。", "参数错误")
        
        valid_events, valid_work_exp, valid_cog, errors = _validate_params(
            short_term, events, work_exp, cognition, reminders, project_state
        )
        
        if errors:
            return error_response("❌ 参数校验失败:\n" + "\n".join(f"  - {e}" for e in errors), "参数错误")
        
        # 检查是否启用 PurrMemo
        from src.loader.purrmemo_client import is_enabled
        use_purrmemo = is_enabled()
        
        if use_purrmemo:
            # PurrMemo 模式：仅推送到 PurrMemo API
            try:
                purrmemo_ok = _push_to_purrmemo(
                    events=valid_events,
                    work_exp=valid_work_exp,
                    cognition=valid_cog,
                    reminders=reminders,
                    project_state=project_state
                )
                if purrmemo_ok:
                    return text_response(
                        {"message": "备忘录已同步到 PurrMemo 记忆系统"},
                        "同步到 PurrMemo"
                    )
                else:
                    return error_response(
                        "PurrMemo 推送失败，请检查 PurrMemo 服务状态",
                        "推送失败"
                    )
            except Exception as e:
                return error_response(f"PurrMemo 推送异常: {e}", "推送异常")
        
        # Legacy 模式：写入本地 memory.md
        flush_data = build_flush_data(
            events=valid_events,
            work_exp=valid_work_exp,
            cognition=valid_cog,
            reminders=reminders,
            project_state=project_state
        )
        
        if flush_data:
            _update_core_information(flush_data)
        
        return text_response(
            {"message": "备忘录更新成功", "short_term": short_term[:100] + "..." if len(short_term) > 100 else short_term},
            "更新成功"
        )
        
    except Exception as e:
        # 【关键】捕获所有异常，格式化为模型可读的错误，而不是让程序崩溃
        traceback.print_exc()
        return error_response(f"备忘录运行时异常: {str(e)}", "执行失败")
"""Memo 工具主入口 - 统一记忆工具，支持写入和搜索"""

import traceback
from src.tool.utils.format import text_response, error_response, warning_response
from src.tool.memo.memo_operations import _validate_params, _write_to_pending
from src.memory.purrmemo import get_memory_client


def Memo(action: str = None, memo_data: dict = None, query: str = None,
         filter: str = None, topk: int = 5, **kwargs) -> str:
    """
    统一记忆工具，支持写入记忆或搜索记忆

    Args:
        action: 操作类型，add=写入记忆，search=搜索记忆（必填）
        memo_data: 记忆数据（action=add时必填），格式：
            {
                "short_term": "...",
                "events": [{"time": "YYYYMMDDHHMM", "event": "..."}],
                "work_exp": ["..."],
                "cognition": ["..."],
                "reminders": "...",
                "project_state": "..."
            }
        query: 搜索语句（action=search时必填）
        filter: 日期过滤（action=search时可选），格式 YYYY-MM-DD
        topk: 返回数量（action=search时可选），默认5

    Returns:
        格式化后的 JSON 字符串
    """
    try:
        if action is None:
            return error_response(
                "缺少必需参数: action（操作类型）\naction=add 时：写入记忆，需要 memo_data\naction=search 时：搜索记忆，需要 query",
                "❌ 参数错误：缺少action"
            )

        if not isinstance(action, str):
            return error_response(
                f"参数类型错误: action 必须是字符串类型，你传入了 {type(action).__name__}",
                "❌ 参数类型错误"
            )

        action = action.strip().lower()

        if action not in ["add", "search"]:
            return error_response(
                f"无效的 action 值: {action}。支持的 action: add, search",
                "❌ 无效的action"
            )

        if action == "add":
            return _handle_add(memo_data)
        elif action == "search":
            return _handle_search(query, filter, topk)

        return error_response("未知错误", "❌ 系统错误")

    except Exception as e:
        traceback.print_exc()
        return error_response(f"记忆工具运行时异常: {str(e)}", "❌ Memo执行异常")


def _handle_add(memo_data: dict = None) -> str:
    """处理写入记忆"""
    if memo_data is None:
        return error_response(
            "action=add 时缺少必需参数: memo_data\nmemo_data 格式：\n{\n    \"short_term\": \"当前工作上下文（必填）\",\n    \"events\": [{\"time\": \"YYYYMMDDHHMM\", \"event\": \"...\"}],\n    \"work_exp\": [\"经验1\", \"经验2\"],\n    \"cognition\": [\"认知1\", \"认知2\"],\n    \"reminders\": \"待办提醒\",\n    \"project_state\": \"项目状态\"\n}",
            "❌ 参数错误：缺少memo_data"
        )

    if not isinstance(memo_data, dict):
        return error_response(
            f"参数类型错误: memo_data 必须是对象类型，你传入了 {type(memo_data).__name__}",
            "❌ 参数类型错误"
        )

    short_term = memo_data.get("short_term")
    events = memo_data.get("events")
    work_exp = memo_data.get("work_exp")
    cognition = memo_data.get("cognition")
    reminders = memo_data.get("reminders")
    project_state = memo_data.get("project_state")

    if not short_term or not short_term.strip():
        return error_response(
            "memo_data.short_term 不能为空",
            "❌ 参数错误：short_term不能为空"
        )

    if events is not None and not isinstance(events, list):
        return error_response(
            f"参数类型错误: memo_data.events 必须是数组类型，你传入了 {type(events).__name__}",
            "❌ 参数类型错误"
        )

    if work_exp is not None and not isinstance(work_exp, list):
        return error_response(
            f"参数类型错误: memo_data.work_exp 必须是数组类型，你传入了 {type(work_exp).__name__}",
            "❌ 参数类型错误"
        )

    if cognition is not None and not isinstance(cognition, list):
        return error_response(
            f"参数类型错误: memo_data.cognition 必须是数组类型，你传入了 {type(cognition).__name__}",
            "❌ 参数类型错误"
        )

    valid_events, valid_work_exp, valid_cog, errors = _validate_params(
        short_term, events, work_exp, cognition, reminders, project_state
    )

    if errors:
        return error_response(
            "参数校验失败:\n" + "\n".join(f"  - {e}" for e in errors),
            "❌ 参数校验失败"
        )

    filepath = _write_to_pending(
        short_term=short_term,
        events=valid_events,
        work_exp=valid_work_exp,
        cognition=valid_cog,
        reminders=reminders,
        project_state=project_state
    )

    return text_response(
        {"message": "记忆已投递至待处理区，后台正在异步加工", "pending_file": filepath},
        "🧠 记忆投递成功"
    )


def _handle_search(query: str = None, filter: str = None, topk: int = 5) -> str:
    """处理搜索记忆"""
    if query is None:
        return error_response(
            "action=search 时缺少必需参数: query",
            "❌ 参数错误：缺少query"
        )

    if not isinstance(query, str):
        return error_response(
            f"参数类型错误: query 必须是字符串类型，你传入了 {type(query).__name__}",
            "❌ 参数类型错误"
        )

    query = query.strip()
    if not query:
        return error_response(
            "参数错误: query 不能为空",
            "❌ 参数校验失败"
        )

    if not isinstance(topk, int):
        return error_response(
            f"参数类型错误: topk 必须是整数类型，你传入了 {type(topk).__name__}",
            "❌ 参数类型错误"
        )

    if topk < 1:
        return error_response(
            "参数错误: topk 必须是正整数",
            "❌ 参数校验失败"
        )

    if filter is not None:
        if not isinstance(filter, str):
            return error_response(
                f"参数类型错误: filter 必须是字符串类型，你传入了 {type(filter).__name__}",
                "❌ 参数类型错误"
            )

        filter = filter.strip()
        if filter and not _validate_date_format(filter):
            return error_response(
                f"参数格式错误: filter 日期格式不正确，应为 YYYY-MM-DD，你传入的是 {filter}",
                "❌ 参数格式错误"
            )

    try:
        client = get_memory_client()
        result = client.search(
            query=query,
            filter_date=filter if filter else None,
            topk=topk
        )

        return text_response(
            {"result": result},
            "🔍 记忆检索成功"
        )

    except Exception as e:
        return error_response(f"记忆检索异常: {str(e)}", "❌ MemoSearch执行异常")


def _validate_date_format(date_str: str) -> bool:
    """验证日期格式 YYYY-MM-DD"""
    import re
    pattern = r'^\d{4}-\d{2}-\d{2}$'
    if not re.match(pattern, date_str):
        return False
    try:
        from datetime import datetime
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False

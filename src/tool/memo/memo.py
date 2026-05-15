"""Memo 工具主入口 - 统一记忆工具，支持写入和搜索"""

import json
import traceback

from src.agent.session_store import SessionStore
from src.memory.purrmemo import get_memory_client
from src.tool.memo.memo_operations import (
    _smart_update_memory_md,
    _validate_memo_data,
    _write_to_pending,
)
from src.tool.utils.format import error_response, text_response


def Memo(
    action: str = None, memo_data: dict = None, query: dict = None, **kwargs
) -> str:
    """
    统一记忆工具，支持写入记忆或搜索记忆

    Args:
        action: 操作类型，add=写入记忆，search=搜索记忆（必填）
        memo_data: 记忆数据（action=add时必填）
        query: 搜索参数（action=search时使用），支持字典格式包含 prompt, date, top_k。
               为空时返回最新全局记忆缓存
    """
    try:
        if action is None:
            return error_response(
                "缺少必需参数: action（操作类型）\naction=add 时：写入记忆，需要 memo_data\naction=search 时：搜索记忆，可选传 query",
                "❌ 参数错误：缺少action",
            )

        action = action.strip().lower()

        if action not in ["add", "search"]:
            return error_response(
                f"无效的 action 值: {action}。支持的 action: add, search",
                "❌ 无效的action",
            )

        if action == "add":
            return _handle_add(memo_data)
        elif action == "search":
            return _handle_search(query)

        return error_response("未知错误", "❌ 系统错误")

    except Exception as e:
        traceback.print_exc()
        return error_response(f"记忆工具运行时异常: {str(e)}", "❌ Memo执行异常")


def _handle_add(memo_data: dict = None) -> str:
    """处理写入记忆：完成后返回统计量而非全量JSON内容"""
    if not isinstance(memo_data, dict):
        return error_response("参数类型错误: memo_data 必须是对象", "❌ 参数类型错误")

    valid_data, errors = _validate_memo_data(memo_data)
    if errors:
        return error_response("参数校验失败:\n" + "\n".join(errors), "❌ 参数校验失败")

    events = valid_data["events"]
    work_exp = valid_data["work_exp"]
    cognition = valid_data["cognition"]
    user_profile = valid_data["user_profile"]

    _smart_update_memory_md(work_exp, user_profile)

    _write_to_pending(
        events=events, cognition=cognition, user_profile=user_profile, work_exp=work_exp
    )

    # 不再返回全量有效数据，改为只返回统计信息
    stats = {
        "events_count": len(events),
        "work_exp_count": len(work_exp),
        "cognition_count": len(cognition),
        "user_profile_count": len(user_profile),
    }
    return text_response(
        {
            "message": "长期记忆已归档并投递至后台存入 MD/SQL/图谱，而 short_term 字段已正常返回",
            "stats": stats,
        },
        f"🧠 记忆归档成功：\n{json.dumps(stats, ensure_ascii=False, indent=2)}",
    )


def _handle_search(query: dict = None) -> str:
    """处理搜索记忆：支持空参数直接获取全局常驻缓存"""

    # 1. 如果不传 query 参数，直接返回全局最新的缓存记忆 (self.memo内容)
    if not query:
        memo_list = SessionStore.load_global_memo()
        return text_response(
            {"memo_cache": memo_list}, "🔍 未提供 query 参数，直接返回最新缓存记忆。"
        )

    if not isinstance(query, dict):
        return error_response(
            "参数错误: query 参数必须是 JSON 对象格式", "❌ 参数类型错误"
        )

    prompt = query.get("prompt", "")
    date_filter = query.get("date")
    top_k = query.get("top_k", 5)

    # 2. 如果传了但 prompt 和 date 都为空，进行报错引导
    if not prompt and not date_filter:
        return error_response(
            "参数缺失: search 操作如果您想全局检索，请在 query 中提供 `prompt` 或 `date`。如果您想获取最近缓存记忆，请不要传递任何 `query` 字段。",
            "❌ 搜索参数校验失败",
        )

    if date_filter and not _validate_date_format(date_filter):
        return error_response(
            "参数格式错误: date 日期格式不正确，应为 YYYY-MM-DD", "❌ 参数格式错误"
        )

    try:
        print(
            f"🔍 [MemoSearch] 开始检索 | prompt={prompt!r} | date={date_filter} | top_k={top_k}"
        )
        client = get_memory_client()
        filters = {"top_k": top_k}
        if date_filter:
            filters["date"] = date_filter

        print(
            f"🔍 [MemoSearch] 调用 client.search | query={prompt!r} | filters={filters}"
        )
        result = client.search(query=prompt, filters=filters)
        print(
            f"🔍 [MemoSearch] client.search 返回 | result长度={len(result) if result else 0}"
        )

        return text_response({"result": result}, "🔍 记忆检索成功")

    except Exception as e:
        print(f"❌ [MemoSearch] 异常: {e}")
        traceback.print_exc()
        return error_response(f"记忆检索异常: {str(e)}", "❌ MemoSearch执行异常")


def _validate_date_format(date_str: str) -> bool:
    """验证日期格式 YYYY-MM-DD"""
    import re
    from datetime import datetime

    pattern = r"^\d{4}-\d{2}-\d{2}$"
    if not re.match(pattern, date_str):
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False

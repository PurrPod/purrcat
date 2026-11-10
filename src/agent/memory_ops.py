"""记忆压缩触发与 Memo 缓存同步。"""

from __future__ import annotations

from src.agent.compression import (
    COMPRESSION_INSTRUCTION,
    SUMMARY_FALLBACK,
    main_warning,
    rebuild_main_history,
    run_summary_attempts,
)
from src.agent.session_store import SessionStore
from src.utils.config import get_model_max_token


def maybe_update_memo(agent, tool_name: str, arguments: dict) -> None:
    """模型调用 Memo add 后同步内存缓存，并在窗口超限时强制压缩。"""
    if tool_name != "Memo" or arguments.get("action") != "add":
        return
    memo_data = arguments.get("memo_data")
    if not memo_data:
        return

    agent.memo.append(memo_data)
    if len(agent.memo) > 30:
        agent.memo = agent.memo[-30:]
    SessionStore.save_global_memo(agent.memo)

    max_tokens = get_model_max_token(agent.name)
    if agent.window_token >= max_tokens:
        agent._truncate_memory_if_needed(force=True)


def truncate_memory_if_needed(agent, force=False) -> None:
    max_tokens = get_model_max_token(agent.name)
    if not force and agent.window_token < max_tokens:
        return

    print(
        f"[Truncate] 触发记忆截断 (当前约 {agent.window_token} tokens)，正在进入内部交互请求模型进行全局大总结..."
    )

    with agent._history_lock:
        raw_history = agent.current_history.copy()
    temp_history = agent._prepare_history_for_model(raw_history)

    summary_text = run_summary_attempts(
        lambda messages: agent.model.chat(
            messages=messages,
            tools=agent._get_tool_schema(),
            cancel_event=agent._tool_interrupt_event,
        ),
        temp_history,
        instruction=COMPRESSION_INSTRUCTION,
        warning_text=main_warning,
        fallback_text=SUMMARY_FALLBACK,
        warning_prefix="[Warn.MemCompress]",
        error_prefix="[Error] 记忆总结网络请求失败",
        parse_error_prefix="[Warn] 解析 Memo 参数失败",
    )

    try:
        with agent._history_lock:
            fresh_system_content = agent._build_system_prompt()
            agent.current_history = rebuild_main_history(
                fresh_system_content, summary_text
            )

        print("[Success] Agent 记忆大总结与安全截断完毕！")
        agent.window_token = 0
        agent.save_checkpoint()

    except Exception as e:
        print(f"[Error] 记忆重组发生严重异常: {e}")

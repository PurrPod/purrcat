"""按本轮输入做后台预搜索，并在相关度足够时注入提示。"""

from __future__ import annotations

import threading


def spawn_hint_search(agent, merged_input: str, task_id: int) -> None:
    threading.Thread(
        target=agent._background_hint_check,
        args=(merged_input, task_id),
        daemon=True,
    ).start()


def background_check(agent, merged_input: str, task_id: int) -> None:
    if getattr(agent, "_bg_search_task_id", None) != task_id:
        return

    try:
        from src.tool.search.skill_search import search_skills
        from src.tool.search.mcp_search import mcp_search
        from src.memory.purrmemo.client import get_memory_client
        import time

        skill_res, _ = search_skills(merged_input, top_k=5)
        mcp_res, _ = mcp_search(merged_input, max_results=5)

        high_score_skills = len([s for s in skill_res if s.get("score", 0) >= 0.5])
        high_score_mcps = len([m for m in mcp_res if m.get("score", 0) >= 0.5])
        total_tools = high_score_skills + high_score_mcps

        if getattr(agent, "_bg_search_task_id", None) != task_id:
            return

        client = get_memory_client()
        valid_memos = 0
        if client.search_tool.vector_engine:
            exps = client.search_tool.vector_engine.search_experiences(
                merged_input, top_k=5
            )
            valid_exps = len([e for e in exps if e.get("score", 0.0) >= 0.5])

            events = client.search_tool.vector_engine.search_events_vector(
                merged_input, top_k=5
            )
            valid_events = len([e for e in events if e.get("score", 0.0) >= 0.5])

            valid_memos = valid_exps + valid_events

        if total_tools == 0 and valid_memos == 0:
            return

        time.sleep(10)

        if (
            getattr(agent, "_bg_search_task_id", None) != task_id
            or agent.state != "handling"
        ):
            return

        already_searched = False
        already_memo_searched = False
        with agent._history_lock:
            for msg in reversed(agent.current_history):
                if msg.get("role") == "user":
                    break
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    for tc in msg.get("tool_calls"):
                        func_name = tc.get("function", {}).get("name", "")
                        args_str = tc.get("function", {}).get("arguments", "")
                        if func_name == "Search" and any(
                            r in args_str for r in ["local", "skill", "mcp"]
                        ):
                            already_searched = True
                        elif (
                            func_name == "Memo"
                            and '"action":"search"' in args_str.replace(" ", "")
                        ):
                            already_memo_searched = True

        hints = []
        if not already_searched and total_tools > 0:
            hints.append(
                f"检查到有 {total_tools} 条 skill/mcp 与本轮对话的总输入语义高度相关，"
                "可以尝试使用 Search 工具(route='local')检索相关数据。"
            )
        if not already_memo_searched and valid_memos > 0:
            hints.append(
                f"检查到记忆库中有 {valid_memos} 条经验/事件与本轮对话的总输入高度相关，"
                "可以尝试使用 Memo 工具(action='search')检索。"
            )

        if hints:
            agent.force_push("\n\n".join(hints), type="system")
    except Exception as e:
        print(f"[Warn] 后台预搜索线程异常: {e}")

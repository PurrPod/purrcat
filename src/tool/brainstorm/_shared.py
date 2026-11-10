"""BrainStorm 的计划渲染与 tool_calls 补全纯函数。"""

from __future__ import annotations

from datetime import datetime


def render_plan_markdown(
    main_plan: list = None,
    sub_branches: list = None,
    now: datetime | None = None,
) -> str:
    """把 BrainStorm 指定的计划解析成 Markdown 总计划，供会话级 @PLAN 引用。"""
    main_plan = main_plan or []
    sub_branches = sub_branches or []
    current = now or datetime.now()

    lines = [
        "# BrainStorm 总计划",
        "",
        f"- 刷新时间：{current.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 主干步骤：{len(main_plan)} 步",
        f"- 后台支线：{len(sub_branches)} 个",
        "",
        "## 主干 Main 分支执行大纲",
    ]
    if main_plan:
        lines.extend(f"{i}. {step}" for i, step in enumerate(main_plan, 1))
    else:
        lines.append("（无）")

    lines.extend(["", "## 后台支线任务"])
    if sub_branches:
        for branch in sub_branches:
            lines.append(f"### {branch.get('branch_id', '未命名支线')}")
            lines.append(f"- 任务：{branch.get('action', '')}")
            lines.append("- 交付物：")
            deliverables = branch.get("deliverable") or []
            if deliverables:
                lines.extend(f"  - `{item}`" for item in deliverables)
            else:
                lines.append("  （无）")
            depends_on = branch.get("depends_on") or []
            lines.append(f"- 依赖：{'、'.join(depends_on) if depends_on else '无'}")
            lines.append("")
    else:
        lines.append("（无）")

    return "\n".join(lines).rstrip() + "\n"


def build_create_message(
    main_plan: list = None, sub_branches: list = None, plan_error: str | None = None
) -> str:
    """拼接 create 动作的回执文案；plan_error 落在支线信息之后。"""
    msg_lines = ["🚀 [系统] 脑暴大纲与任务排期已成功落盘生效！"]

    if main_plan:
        msg_lines.append("\n### 📌 【主干 Main 分支后续执行大纲】")
        for i, step in enumerate(main_plan, 1):
            msg_lines.append(f"**Step {i}**. {step}")

    if sub_branches:
        msg_lines.append(
            f"\n后台支线任务 ({len(sub_branches)}个) 已成功递交底层引擎，"
            "在暗中开辟独立线程快马加鞭运转中。"
        )

    if plan_error:
        msg_lines.append(f"\n⚠️ 总计划落盘失败：{plan_error}")

    msg_lines.append(
        "\n💡 指示：工具已闭环，你不需要进行任何循环查询。"
        "请立即按照你刚才定下的 Main 主线计划第一步去沙盒开展工作。"
        "子任务结果出来后系统会自动通知。"
    )
    return "\n".join(msg_lines)


def find_assistant_tool_batch(history: list) -> int:
    """从尾部定位最近一条带 tool_calls 的 assistant 消息索引，找不到返回 -1。"""
    for i in range(len(history) - 1, -1, -1):
        msg = history[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            return i
    return -1


def unanswered_tool_calls(history: list, assistant_idx: int) -> tuple[set, list]:
    """返回该 assistant 批次中已应答的 id 集合与仍未应答的调用。"""
    if assistant_idx < 0 or assistant_idx >= len(history):
        return set(), []

    assistant_msg = history[assistant_idx]
    answered_ids = {
        msg.get("tool_call_id")
        for msg in history[assistant_idx + 1 :]
        if msg.get("role") == "tool"
    }
    unanswered = [
        tc
        for tc in assistant_msg.get("tool_calls", [])
        if tc.get("id") not in answered_ids
    ]
    return answered_ids, unanswered


def pick_own_tool_call(calls: list, tool_call_id: str | None) -> dict | None:
    """优先按调度器注入的 id 匹配本工具调用，兜底按函数名匹配。"""
    if tool_call_id:
        for tc in calls:
            if tc.get("id") == tool_call_id:
                return tc

    for tc in calls:
        if tc.get("function", {}).get("name") == "BrainStorm":
            return tc
    return None


def build_tool_reply(tool_call: dict, content: str, name: str | None = None) -> dict:
    """构造 OpenAI 格式的 tool 响应条目。"""
    return {
        "role": "tool",
        "tool_call_id": tool_call.get("id"),
        "name": name or tool_call.get("function", {}).get("name", ""),
        "content": content,
    }

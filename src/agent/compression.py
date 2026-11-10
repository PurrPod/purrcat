"""记忆压缩（大总结）的提示词、模型交互与历史重建。

主 Agent 与子代理共用同一套重试与校验逻辑，差异只在提示词文案与日志标签。
"""

from __future__ import annotations

import datetime
import json
from typing import Callable

from src.agent.history import strip_reasoning, system_event

COMPRESSION_INSTRUCTION = (
    "记忆窗口已达上限，系统将要删除所有对话历史。为防止上下文断层，请对当前所有会话细节、"
    "历史、当前工作记忆与进度进行大总结，然后调用 Memo 工具（必须设置 action='add'）传入总结。"
    "系统将仅保留这份总结。"
)

SUMMARY_HEADER = "【历史记忆总结】"

MAIN_SUMMARY_FALLBACK = "（模型未能成功生成有效总结，上下文已强行截断）"
SUB_SUMMARY_FALLBACK = "（后台子分支未能成功生成有效总结，上下文已强行截断）"


def main_warning(attempt: int) -> str:
    return (
        f"【第{attempt}次警告】未使用Memo工具进行记忆总结(或 action 不为 'add')！"
        "请只调用 Memo 工具并将 action 设为 'add'，不要调用其他任何无关工具。"
    )


def sub_warning(attempt: int) -> str:
    return (
        f"【第{attempt}次警告】未使用Memo工具进行记忆总结(或 action 不为 'add')！"
        "请只调用 Memo 工具并将 action 设为 'add'，不要完成无关工作。"
    )


def compression_prompt(instruction: str, now: datetime.datetime | None = None) -> dict:
    """把压缩指令包装成模型可读的 system 事件消息。"""
    return system_event(instruction, now=now)


def extract_memo_summary(
    msg_resp, *, parse_error_prefix: str | None = None
) -> tuple[str | None, bool]:
    """从模型回复的 Memo(action=add) 调用中提取总结文本。"""
    if not getattr(msg_resp, "tool_calls", None):
        return None, False
    for tc in msg_resp.tool_calls:
        if tc.function.name != "Memo":
            continue
        try:
            args = json.loads(tc.function.arguments)
        except Exception as e:
            if parse_error_prefix:
                print(f"{parse_error_prefix}: {e}")
            continue
        if args.get("action") == "add" and args.get("memo_data"):
            data = args["memo_data"]
            text = (
                json.dumps(data, ensure_ascii=False)
                if isinstance(data, dict)
                else str(data)
            )
            return text, True
    return None, False


def run_summary_attempts(
    chat_fn: Callable[[list[dict]], object],
    messages: list[dict],
    *,
    instruction: str,
    warning_text: Callable[[int], str],
    fallback_text: str,
    warning_prefix: str,
    error_prefix: str,
    parse_error_prefix: str | None = None,
    max_retries: int = 3,
    now: datetime.datetime | None = None,
) -> str:
    """反复请求模型产出 Memo 总结，失败时追加警告重试。

    会就地修改 messages（追加 warning）。返回最终总结文本。
    """
    messages.append(compression_prompt(instruction, now=now))

    summary_text = None
    msg_resp = None

    for attempt in range(1, max_retries + 1):
        try:
            response = chat_fn(messages)
            msg_resp = response.choices[0].message
            summary_text, valid = extract_memo_summary(
                msg_resp, parse_error_prefix=parse_error_prefix
            )
            if valid:
                break

            warning_msg = warning_text(attempt)
            messages.append(system_event(warning_msg))
            print(f"{warning_prefix} {warning_msg}")
        except Exception as e:
            print(f"{error_prefix}: {e}")
            break

    if not summary_text:
        if msg_resp is not None and msg_resp.content:
            summary_text = msg_resp.content
        else:
            summary_text = fallback_text
    return summary_text


def rebuild_main_history(
    system_prompt: str,
    summary_text: str,
    now: datetime.datetime | None = None,
) -> list[dict]:
    """主 Agent 压缩后的历史：新系统提示词 + 总结。"""
    return [
        {"role": "system", "content": system_prompt},
        system_event(f"{SUMMARY_HEADER}\n{summary_text}", now=now),
    ]


def find_safe_split_index(messages: list[dict], keep_recent: int = 10) -> int:
    """从尾部保留 keep_recent 条，向前推移到不截断工具链的安全位置。"""
    split_idx = len(messages) - keep_recent
    if split_idx > 1:
        while split_idx > 1:
            curr_msg = messages[split_idx]
            prev_msg = messages[split_idx - 1]
            if curr_msg.get("role") == "tool":
                split_idx -= 1
                continue
            if prev_msg.get("role") == "assistant" and prev_msg.get("tool_calls"):
                split_idx -= 1
                continue
            break
    if split_idx < 1:
        split_idx = 1
    return split_idx


def rebuild_sub_history(
    messages: list[dict],
    system_prompt: str,
    summary_text: str,
    *,
    keep_recent: int = 10,
    now: datetime.datetime | None = None,
) -> list[dict]:
    """子代理压缩后的历史：新系统提示词 + 最近消息 + 总结。"""
    split_idx = find_safe_split_index(messages, keep_recent)
    recent_messages = messages[split_idx:]
    history = (
        [{"role": "system", "content": system_prompt}]
        + recent_messages
        + [system_event(f"{SUMMARY_HEADER}\n{summary_text}", now=now)]
    )
    strip_reasoning(history)
    return history

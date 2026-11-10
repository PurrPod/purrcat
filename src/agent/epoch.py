"""单个 epoch 的模型流消费、usage 记账与 assistant 落盘。"""

from __future__ import annotations

from src.agent.streaming import StreamAssembler
from src.agent.tool_calls import build_assistant_message, record_tool_usage
from src.agent.history import workflow_hint
from src.utils.attachments import materialize_message
from src.utils.config import get_model_max_token


def prepare_history_for_model(messages):
    """发送模型前：把历史里的图片副本路径还原成 base64"""
    return [materialize_message(msg) for msg in messages]


def record_usage(agent, usage) -> None:
    agent.window_token = usage.total_tokens
    # 🌟 累计本会话消耗（子代理在 SubAgentRunner 中另行累计）
    agent.consumed_tokens += getattr(usage, "total_tokens", 0) or 0
    # 🌟 ACP 总线：上下文用量（编辑器侧 usage_update 词汇）
    from src.server.acp.bus import get_bus

    get_bus().publish(
        agent.session_id,
        "usage",
        {
            "used": agent.window_token,
            "size": get_model_max_token(agent.name),
        },
    )


def chat_stream(agent, messages, tools, interaction_id):
    """流式调用主模型；流式链路异常时回退到非流式调用。"""
    try:
        agent._set_live_phase("thinking")
        return agent._consume_stream(messages, tools, interaction_id)
    except InterruptedError:
        # 用户打断：不做非流式兜底重试，直接上抛让主循环静默收尾
        raise
    except Exception as e:
        if agent._get_current_interaction_id() != interaction_id:
            # 打断/会话切换引起的流中断：结果会被上层丢弃，无需回退
            raise
        print(f"[Warn.Stream] 流式调用失败，回退非流式重试: {e}")
        agent._live_reasoning = ""
        response = agent.model.chat(
            messages=messages, tools=tools, cancel_event=agent._tool_interrupt_event
        )
        return response.choices[0].message, getattr(response, "usage", None)


def consume_stream(agent, messages, tools, interaction_id):
    """消费流式分片并拼装成与非流式等价的 message。"""
    agent._live_reasoning = ""
    response = agent.model.chat(
        messages=messages,
        tools=tools,
        stream=True,
        cancel_event=agent._tool_interrupt_event,
    )

    assembler = StreamAssembler()
    for chunk in response:
        if agent._get_current_interaction_id() != interaction_id:
            # 人类打断/会话切换：提前掐断流，拼装结果将被上层丢弃
            break
        assembler.add(chunk)
        if assembler.reasoning_text:
            agent._live_reasoning = assembler.reasoning_text

    agent._live_reasoning = ""
    return assembler.build(), assembler.usage


def process_assistant_message(agent, msg_resp) -> bool:
    assist_msg = build_assistant_message(msg_resp)
    rc = assist_msg.get("reasoning_content")
    agent._append_history(assist_msg)
    # 🌟 ACP 总线：思考/消息事件（与旧 sensor 网关并存，Phase 4 删旧路径）
    from src.server.acp.bus import get_bus

    if rc:
        get_bus().publish(agent.session_id, "agent_thought", {"text": rc})
    if msg_resp.content:
        get_bus().publish(agent.session_id, "agent_message", {"text": msg_resp.content})

    return bool(msg_resp.tool_calls)


def run_epoch(
    agent, interaction_id: int, loop_epoch: int, used_tools: dict, loop_end_retry: int
) -> str:
    """执行一轮模型调用与工具/钩子处理，返回 break / continue / retry。"""
    agent._checker()

    with agent._history_lock:
        raw_history = list(agent.current_history)

    # 图片副本在这里按需还原成 base64；整体超限则改用视觉模型转述
    safe_history = agent._prepare_history_for_model(raw_history)

    msg_resp, usage = agent._chat_stream(
        safe_history, agent._get_tool_schema(), interaction_id
    )

    if agent._get_current_interaction_id() != interaction_id:
        print("[Warn.Session] 网络响应返回后检测到交互ID过期，丢弃响应")
        return "break"

    if usage is not None:
        agent._record_usage(usage)
    has_tools = agent._process_assistant_message(msg_resp)

    # 本次消息发起的那一批工具调用（on_tool_calling 的 tool_use_check 只查这一批）
    current_tools = record_tool_usage(msg_resp.tool_calls, used_tools)

    if has_tools:
        should_pause = agent._execute_tool_calls(msg_resp.tool_calls)
        all_tool_success = agent._inject_hook_results(
            "on_tool_calling",
            epoch=loop_epoch,
            used_tools=current_tools,  # 只看本次调用的工具
        )
        if not all_tool_success:
            return "continue"
        if should_pause:
            return "break"
        return "continue"

    all_success = agent._inject_hook_results(
        "on_loop_end",
        epoch=loop_epoch,
        used_tools=used_tools,
        loop_end_retry=loop_end_retry,
    )
    if all_success:
        print("[Debug] 所有条件及拦截器检验通过，正常关闭循环。")
        return "break"

    agent._append_history(workflow_hint("未满足结束循环条件，已自动打回"))
    # 🌟 打回提示是 workflow_hint 系统注入，不算收到用户输入，不触发钩子
    print(f"[Debug] 当前第 {loop_epoch} 轮条件不足，被打回重新触发模型迭代。")
    return "retry"

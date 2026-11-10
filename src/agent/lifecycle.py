"""主 Agent 交互生命周期：开始、主循环、收尾与异常收口。"""

from __future__ import annotations


def process_message(agent) -> None:
    interaction_id = begin_interaction(agent)
    merged_input = merged_user_input(agent)
    if merged_input:
        agent._inject_hook_results("on_loop_start", epoch=0)
        agent._spawn_hint_search(merged_input, interaction_id)

    turn_ended = run_agent_loop(agent, interaction_id)
    finish_turn(agent, turn_ended)


def begin_interaction(agent) -> int:
    current_interaction_id = agent._increment_interaction_id()
    agent._bg_search_task_id = current_interaction_id
    # 清理上一轮遗留的打断信号，避免新交互的工具被误杀
    agent._tool_interrupt_event.clear()
    return current_interaction_id


def merged_user_input(agent) -> str:
    user_texts = [
        msg["content"] for msg in agent.pending_force_push if msg.get("type") == "user"
    ]
    return " ".join(user_texts).strip()


def run_agent_loop(agent, interaction_id: int) -> bool:
    used_tools = {}
    loop_epoch = 0
    loop_end_retry = 0
    turn_ended = False  # 打断/断层路径已在 _handle_interaction_error 发过 turn_end
    agent._check_and_fix_toolchain()
    while True:
        try:
            loop_epoch += 1
            agent._inject_hook_results("on_loop_epoch", epoch=loop_epoch)
            if agent._get_current_interaction_id() != interaction_id:
                print(
                    "[Warn.Session] 检测到交互ID过期 "
                    f"({interaction_id} != {agent._get_current_interaction_id()})，"
                    "丢弃旧响应"
                )
                break

            action = agent._run_epoch(
                interaction_id, loop_epoch, used_tools, loop_end_retry
            )
            if action == "break":
                break
            if action == "retry":
                loop_end_retry += 1

        except (KeyboardInterrupt, InterruptedError):
            # 用户强制打断（含模型调用重试期间被打断）：不写入交互断层，只记录打断标记
            handle_interaction_error(agent, is_interrupt=True)
            turn_ended = True
            break
        except Exception as e:
            handle_interaction_error(agent, e=e)
            turn_ended = True
            break

    return turn_ended


def finish_turn(agent, turn_ended: bool) -> None:
    agent._set_live_phase("idle")
    # 🌟 ACP 总线：一轮交互结束，SSE 消费方据此补 prompt 的 stopReason
    if not turn_ended:
        from src.server.acp.bus import get_bus

        get_bus().publish(agent.session_id, "turn_end", {"stopReason": "end_turn"})
    agent.save_checkpoint()


def handle_interaction_error(agent, e=None, is_interrupt=False) -> None:
    content_msg = (
        "[Warn.Interrupt] 运行被强制中断。"
        if is_interrupt
        else f"[Error.Fault] 交互断层: {e}"
    )
    print(content_msg)

    agent._check_and_fix_toolchain()

    agent._append_history({"role": "assistant", "content": content_msg})

    # 🌟 ACP 总线：非正常收尾（打断/断层）也要发 turn_end，SSE 消费方才能补 stopReason
    # 规范 stopReason 枚举无 error：打断→cancelled，故障→end_turn（错误文本已走消息通道）
    from src.server.acp.bus import get_bus

    get_bus().publish(
        agent.session_id,
        "turn_end",
        {
            "stopReason": "cancelled" if is_interrupt else "end_turn",
            "message": content_msg,
        },
    )

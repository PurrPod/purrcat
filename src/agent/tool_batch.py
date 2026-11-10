"""工具批次执行与 tool 响应落盘。"""

from __future__ import annotations

import json

from src.agent.tool_calls import (
    PARAM_DAMAGED_MESSAGE,
    order_for_execution,
    parse_arguments,
    with_system_arguments,
)
from src.utils.attachments import (
    materialize_message,
    max_request_bytes,
    serialized_size,
)
from src.utils.config import get_main_model_config


def vision_request_limit(agent) -> int:
    return max_request_bytes(get_main_model_config(agent.name))


def materialized_request_bytes(agent) -> int:
    """当前历史还原图片后的序列化体积，供 Task 直注前估算"""
    with agent._history_lock:
        raw_history = list(agent.current_history)
    return serialized_size([materialize_message(msg) for msg in raw_history])


class ToolBatchExecutor:
    """按批次执行工具；BrainStorm(create) 延后到批次末尾。"""

    def __init__(self, agent, *, dispatch, extract_content, build_display):
        self._agent = agent
        self._dispatch = dispatch
        self._extract_content = extract_content
        self._build_display = build_display

    def execute(self, tool_calls, run_one) -> bool:
        self._agent._set_live_phase("processing")
        # 🌟 快照派发类工具（BrainStorm create）延后到批次末尾执行：
        # 确保同批次其它工具的返回结果先写入 history，BS 随后的快照才能完整兜住
        for tool_call in order_for_execution(tool_calls):
            if run_one(tool_call):
                break
        return False

    def execute_one(self, tool_call) -> bool:
        """执行单个工具并写入 tool 响应；返回 True 表示因人类打断而终止后续工具。"""
        agent = self._agent
        target_tool_name = tool_call.function.name
        arguments = parse_arguments(tool_call.function.arguments)
        if arguments is None:
            agent._append_history(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": target_tool_name,
                    "content": PARAM_DAMAGED_MESSAGE,
                }
            )
            return False

        vision = getattr(agent.model, "vision", False)
        needs_vision_request_meta = target_tool_name == "Task" and vision
        arguments = with_system_arguments(
            target_tool_name,
            arguments,
            session_id=agent.session_id,
            tool_call_id=tool_call.id,
            vision=vision,
            request_bytes=(
                agent._materialized_request_bytes()
                if needs_vision_request_meta
                else None
            ),
            request_limit_bytes=(
                agent._vision_request_limit() if needs_vision_request_meta else None
            ),
        )

        current_iid = agent._get_current_interaction_id()
        try:
            result_content = self._dispatch(
                target_tool_name,
                arguments,
                cancel_event=agent._tool_interrupt_event,
                # 🌟 主模型开启 vision 直注时，工具输出图片不落盘直接注入对话
                vision_mode=getattr(agent.model, "vision", False),
            )
        except Exception as e:
            result_content = json.dumps(
                {"error": f"工具执行异常: {str(e)}", "type": "error"},
                ensure_ascii=False,
            )
            print(f"[Warn.Tool] 工具 {target_tool_name} 执行抛出异常: {e}")

        if agent._get_current_interaction_id() != current_iid:
            # 🌟 区分两种场景：
            # a) 人类强制打断：伪造结果必须写进 history，保证 assistant.tool_calls 有配对的
            #    tool 响应（否则下轮 LLM 调用会被 API 以 toolchain 不完整拒绝），并停止执行后续工具
            # b) 会话切换：保持原有的丢弃幽灵结果行为（避免污染新会话的 history）
            if agent._tool_interrupt_event.is_set():
                print(
                    f"[Lock.Interrupt] 工具 {target_tool_name} 被人类强行打断，注入打断提示并终止本轮工具链。"
                )
                agent._append_history(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": target_tool_name,
                        "content": self._extract_content(result_content),
                    }
                )
                agent._tool_interrupt_event.clear()
                return True
            print(
                f"[Warn.Interrupt] 工具 {target_tool_name} 执行完毕，但检测到会话已切换或被打断，丢弃幽灵结果。"
            )
            return False

        # 🌟 ACP 总线：工具完成事件——完整结果/参数随载荷透出，
        # dispatch 侧统一截断（编辑器看 tool_call_update.content）；
        # tool_detail 过滤由各桥自决；vision 直注结果先剥离图片 base64 只透出占位文本
        from src.server.acp.bus import get_bus

        get_bus().publish(
            agent.session_id,
            "tool_call",
            {
                "name": target_tool_name,
                "tool_call_id": tool_call.id,
                "arguments": arguments,
                "result": self._build_display(result_content),
            },
        )
        agent._append_history(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": target_tool_name,
                # vision 直注时为 OpenAI 多模态 parts 列表（含 image_url），
                # 普通结果为 JSON 字符串
                "content": self._extract_content(result_content),
            }
        )

        agent._maybe_update_memo(target_tool_name, arguments)
        return False

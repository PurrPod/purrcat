import copy
import datetime
import json
import os
import threading
import time

from src.agent import epoch, hint_search, lifecycle, memory_ops, tool_batch
from src.agent.history import repair_toolchain
from src.agent.hook_handler import HookHandler
from src.agent.session_store import SessionStore
from src.agent.tool_batch import ToolBatchExecutor
from src.agent.tool_calls import is_snapshot_dispatch_tool
from src.model import AgentModel, ChatModel
from src.tool.utils.route import (
    build_display_result,
    dispatch_tool,
    extract_tool_message_content,
)
from src.utils.attachments import snapshot_message
from src.utils.config import BUFFER_DIR, get_agent_model
from src.utils.tracker import Tracker


class Agent:
    def __init__(
        self,
        session_id,
        initial_history=None,
        name=None,
        save_callback=None,
        paradigm_path=None,
        model: ChatModel | None = None,
        hook_handler=None,
        tracker=None,
        memo=None,
    ):
        self.name = name or get_agent_model()
        self.session_id = session_id
        # === 常驻内存记忆缓存（可注入，便于测试） ===
        self.memo = memo if memo is not None else SessionStore.load_global_memo()

        self._state = "idle"
        self._interaction_id = 0
        self.pending_force_push = []
        self.window_token = 0
        # 🌟 本会话累计消耗（所有 LLM 调用 usage.total_tokens 之和，压缩记忆不清零）
        self.consumed_tokens = 0
        self._stop_event = threading.Event()
        # 🌟 工具打断信号：专用于掐断正在执行的工具（与 _stop_event 的永久停机语义分离）
        self._tool_interrupt_event = threading.Event()
        # 🌟 记忆压缩进行中标记（压缩不改 state，供 /status API 区分 idle 但在压缩的情况）
        self._compressing = False
        # 🌟 流式思考内容：模型思考增量实时累积于此（仅供 /status 轮询透出，不落盘不进 toolchain）
        self._live_reasoning = ""
        # 🌟 当前交互阶段：thinking=模型推理中 / processing=工具执行中 / idle=空闲（供前端切换气泡文案）
        self._live_phase = "idle"
        self._history_lock = threading.RLock()
        self._push_lock = threading.RLock()
        # 🌟 「收到输入时」(on_input_received) 钩子执行中标记：钩子自身的注入不再递归触发
        self._in_input_hook = False
        self._save_callback = save_callback
        # 🌟 模型可注入：测试与子流程可替换为 FakeModel，默认仍走全局 Agent 模型
        self.model = model if model is not None else AgentModel(self.session_id)
        self.model.bind_task(self.session_id, "AgentMain")
        self.tracker = tracker if tracker is not None else Tracker()
        self.current_history = initial_history or []
        # 🌟 图片直注的历史只留副本路径：旧会话里的 base64 在加载时一次性迁移到
        # <会话目录>/attachment/，避免恢复会话后继续携带大段 base64
        self.current_history = [
            snapshot_message(msg, session_id) for msg in self.current_history
        ]
        self.hook_handler = (
            hook_handler if hook_handler is not None else HookHandler(paradigm_path)
        )
        if not self.current_history:
            fresh_prompt = self._build_system_prompt()
            self.current_history = [{"role": "system", "content": fresh_prompt}]

    def dump_agent_state(self):
        with self._history_lock:
            return {
                "session_id": self.session_id,
                "current_history": self.current_history,
                "hook_handler_state": self.hook_handler.get_state(),
            }

    def load_agent_state(self, state_dict):
        with self._history_lock:
            self.session_id = state_dict["session_id"]
            self.current_history = state_dict["current_history"]
            self.hook_handler.load_state(state_dict.get("hook_handler_state"))

    def _build_system_prompt(self):
        results = self.hook_handler.execute(
            "on_build_system_prompt", agent=self, epoch=0
        )
        prompt_parts = [
            res["inject_prompt"] for res in results if res.get("inject_prompt")
        ]
        return "\n\n---\n\n".join(prompt_parts)

    def _inject_hook_results(self, stage_name, epoch=0, **kwargs):
        """统一的钩子执行与历史记录注入封装，返回 True 表示全部成功"""
        results = self.hook_handler.execute(
            stage_name, agent=self, epoch=epoch, **kwargs
        )
        all_success = True
        for res in results:
            if not res.get("success"):
                all_success = False
            if res.get("inject_prompt"):
                hint_data = {"type": "workflow_hint", "content": res["inject_prompt"]}
                self._append_history(
                    {
                        "role": "user",
                        "content": json.dumps(hint_data, ensure_ascii=False),
                    }
                )
        # 🌟 此处注入的都是 workflow_hint（系统提示），不算收到用户输入，
        # 不触发「收到输入时」钩子（只有 type=user 的真人输入才触发）
        return all_success

    def _fire_input_received(self, messages):
        """触发「收到输入时」(on_input_received) 钩子。

        messages 是本批以 role=user 注入历史的消息列表：
        元素形如 {"type": ..., "content": ...}，可能只有 1 条，也可能同批多条。
        只有 type=user 的消息算「收到用户输入」，其余（system / workflow_hint 等
        系统注入）一律不触发；钩子自身的注入不再递归触发（_in_input_hook 防重入）。
        """
        messages = [m for m in messages if m.get("type") == "user"]
        if not messages or self._in_input_hook:
            return
        self._in_input_hook = True
        try:
            self._inject_hook_results(
                "on_input_received", epoch=0, received_messages=messages
            )
        finally:
            self._in_input_hook = False

    def stop(self):
        self._stop_event.set()
        if hasattr(self, "model") and self.model:
            self.model.unbind()

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value

    def _set_live_phase(self, phase: str):
        """🌟 ACP 总线：阶段变化事件（thinking/processing/idle）。

        取代裸赋值 self._live_phase = x，保证赋值点与总线事件同点触发；
        构造函数里的初始 idle 不发事件（无消费者）。
        """
        self._live_phase = phase
        try:
            from src.server.acp.bus import get_bus

            get_bus().publish(self.session_id, "phase", {"phase": phase})
        except Exception:
            pass

    def _get_tool_schema(self):
        from src.tool import (
            AGENT_TOOL_SCHEMA,
        )  # 延迟 import，打破与 src.tool 的循环依赖

        return AGENT_TOOL_SCHEMA

    def _get_current_interaction_id(self):
        return self._interaction_id

    def _increment_interaction_id(self):
        self._interaction_id += 1
        return self._interaction_id

    def force_interrupt(self):
        print("[Lock] 触发强行打断！递增交互ID + 激活工具打断信号")
        self._increment_interaction_id()
        self._tool_interrupt_event.set()  # 掐断正在执行的工具（子进程会被物理 terminate）
        # 🌟 不直接写 idle：旧交互（模型调用/工具）还在 unwind，提前报 idle 会让
        # 前端误显示空闲、新消息排队却无人消费（sensor 线程仍被占）。
        # aborting 期间 /status 持续报忙，sensor 收尾后自然回落 idle。
        self.state = "aborting"

    def get_history(self):
        with self._history_lock:
            return copy.deepcopy(self.current_history)

    def _append_history(self, message: dict):
        with self._history_lock:
            self.current_history.append(message)
            try:
                self.tracker.add(message)
                self.save_checkpoint()
            except Exception as e:
                print(f"[Warn.Memory] 落盘失败: {e}")

    @staticmethod
    def _buffer_long_user_input(content, type="user"):
        """对 type=user 的超长输入进行字数检验，超限内容落盘到 buffer，返回替换提示文本。"""
        if type != "user" or len(content) <= 3000:
            return content
        import uuid

        user_input_dir = os.path.join(BUFFER_DIR, "user_input")
        os.makedirs(user_input_dir, exist_ok=True)
        filename = f"{uuid.uuid4().hex[:8]}.txt"
        filepath = os.path.join(user_input_dir, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            print(f"[Warn.Buffer] 超长输入落盘失败: {e}")
            return content
        file_uri = filepath.replace("\\", "/")
        return f"【输入超出字数限制，已将请求内容落盘({file_uri})】"

    def force_push(self, content, type="user"):
        content = self._buffer_long_user_input(content, type)
        with self._push_lock:
            self.pending_force_push.append(
                {
                    "type": type,
                    "time": datetime.datetime.now().strftime("%m-%d %H:%M:%S"),
                    "content": content,
                }
            )

    def force_push_batch(self, events: list):
        """
        批量强制推送消息，避免被 sensor 线程在中间截断
        events 格式示例: [{"content": "消息1", "type": "user"}, {"content": "系统提示", "type": "system"}]
        """
        now_str = datetime.datetime.now().strftime("%m-%d %H:%M:%S")
        batch_push = []
        for event in events:
            event_type = event.get("type", "user")
            event_content = event.get("content", "")
            event_content = self._buffer_long_user_input(event_content, event_type)
            batch_push.append(
                {
                    "type": event_type,
                    "time": now_str,
                    "content": event_content,
                }
            )
        with self._push_lock:
            self.pending_force_push.extend(batch_push)

    def _check_and_fix_toolchain(self):
        """检查并清理断裂的 tool_calls / tool 响应链（逻辑见 history.repair_toolchain）。"""
        if not self.current_history:
            return

        with self._history_lock:
            repair = repair_toolchain(self.current_history)

        if repair is not None:
            print(
                f"[Warn.ToolChain] 检测到未完成的多工具调用链 (请求: {repair.requested}, 实际返回: {repair.answered}, 缺失: {repair.missing}, 多余: {repair.extra})，正在清理并撤回悬空节点..."
            )

    def _checker(self):
        local_push = []
        with self._push_lock:
            if self.pending_force_push:
                local_push = self.pending_force_push.copy()
                self.pending_force_push.clear()
        if local_push:
            self._check_and_fix_toolchain()
            batch_data = {"events": local_push}
            self._append_history(
                {"role": "user", "content": json.dumps(batch_data, ensure_ascii=False)}
            )
            # 🌟 强制注入 / 消费队列：整批（1 条或多条）交给「收到输入时」钩子，
            # 由 _fire_input_received 内部只保留 type=user 的消息（system 等注入不算）
            self._fire_input_received(local_push)

    def process_message(self):
        lifecycle.process_message(self)

    def _begin_interaction(self) -> int:
        return lifecycle.begin_interaction(self)

    def _merged_user_input(self) -> str:
        return lifecycle.merged_user_input(self)

    def _spawn_hint_search(self, merged_input: str, task_id: int):
        hint_search.spawn_hint_search(self, merged_input, task_id)

    def _background_hint_check(self, merged_input: str, task_id: int):
        hint_search.background_check(self, merged_input, task_id)

    def _run_agent_loop(self, interaction_id: int) -> bool:
        return lifecycle.run_agent_loop(self, interaction_id)

    def _run_epoch(
        self,
        interaction_id: int,
        loop_epoch: int,
        used_tools: dict,
        loop_end_retry: int,
    ) -> str:
        """执行一轮模型调用与工具/钩子处理，返回 break / continue / retry。"""
        return epoch.run_epoch(
            self, interaction_id, loop_epoch, used_tools, loop_end_retry
        )

    def _record_usage(self, usage) -> None:
        epoch.record_usage(self, usage)

    def _finish_turn(self, turn_ended: bool) -> None:
        lifecycle.finish_turn(self, turn_ended)

    def _prepare_history_for_model(self, messages):
        """发送模型前：把历史里的图片副本路径还原成 base64"""
        return epoch.prepare_history_for_model(messages)

    def _vision_request_limit(self) -> int:
        return tool_batch.vision_request_limit(self)

    def _materialized_request_bytes(self) -> int:
        """当前历史还原图片后的序列化体积，供 Task 直注前估算"""
        return tool_batch.materialized_request_bytes(self)

    def _chat_stream(self, messages, tools, interaction_id):
        """
        🌟 流式调用主模型（带兜底）：思考增量实时写入 self._live_reasoning
        （供 /status 轮询透出给前端）；流式链路出任何异常时自动回退到
        原有非流式调用，保证 Agent 主循环行为不受影响。
        """
        return epoch.chat_stream(self, messages, tools, interaction_id)

    def _consume_stream(self, messages, tools, interaction_id):
        """
        真正的流式消费与拼装：思考过程不落盘、不进 history/toolchain，
        流结束后拼装出与非流式等价的 message 对象，仍走原有的
        _process_assistant_message 写入路径。
        """
        return epoch.consume_stream(self, messages, tools, interaction_id)

    def _process_assistant_message(self, msg_resp) -> bool:
        return epoch.process_assistant_message(self, msg_resp)

    @staticmethod
    def _is_snapshot_dispatch_tool(tool_call) -> bool:
        """识别「快照主历史并派发子代理」的工具（BrainStorm create）。"""
        return is_snapshot_dispatch_tool(tool_call)

    def _tool_batch_executor(self) -> ToolBatchExecutor:
        return ToolBatchExecutor(
            self,
            dispatch=dispatch_tool,
            extract_content=extract_tool_message_content,
            build_display=build_display_result,
        )

    def _execute_tool_calls(self, tool_calls) -> bool:
        return self._tool_batch_executor().execute(
            tool_calls, self._execute_single_tool
        )

    def _execute_single_tool(self, tool_call) -> bool:
        """执行单个工具并写入 tool 响应；返回 True 表示因人类打断而终止后续工具。"""
        return self._tool_batch_executor().execute_one(tool_call)

    def _maybe_update_memo(self, tool_name: str, arguments: dict) -> None:
        """模型调用 Memo add 后同步内存缓存，并在窗口超限时强制压缩。"""
        memory_ops.maybe_update_memo(self, tool_name, arguments)

    def _handle_interaction_error(self, e=None, is_interrupt=False):
        lifecycle.handle_interaction_error(self, e=e, is_interrupt=is_interrupt)

    def sensor(self):
        print("[Init] Agent 后台主核已启动...")
        while not self._stop_event.is_set():
            try:
                if self.pending_force_push:
                    self.state = "handling"
                    self.process_message()
                self.state = "idle"
                time.sleep(0.5)
            except BaseException as e:
                print(f"[Error] 主核异常已被安全拦截: {e}")
                self.state = "idle"
                time.sleep(1)

    def save_checkpoint(self):
        if self._save_callback:
            self._save_callback()

    def force_compress_memory(self):
        self._compressing = True
        try:
            self._truncate_memory_if_needed(force=True)
        finally:
            self._compressing = False

    def _truncate_memory_if_needed(self, force=False):
        memory_ops.truncate_memory_if_needed(self, force=force)

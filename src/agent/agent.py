import copy
import datetime
import json
import os
import threading
import time

from json_repair import repair_json

from src.agent.session_store import SessionStore
from src.model import AgentModel
from src.tool import AGENT_TOOL_SCHEMA
from src.tool.utils.route import dispatch_tool
from src.utils.config import (
    AGENT_CORE_DIR,
    SOUL_MD_PATH,
    SYSTEM_RULES_DIR,
    get_agent_model,
)
from src.utils.tracker import Tracker

MEMORY_MD_PATH = os.path.join(AGENT_CORE_DIR, "MEMORY.md")


class Agent:
    def __init__(self, session_id, initial_history=None, name=None, save_callback=None):
        self.name = name or get_agent_model()
        self.session_id = session_id
        # === 常驻内存记忆缓存 ===
        self.memo = SessionStore.load_global_memo()
        self._state = "idle"
        self._interaction_id = 0
        self.pending_force_push = []
        self.window_token = 0
        self._stop_event = threading.Event()
        self._history_lock = threading.Lock()
        self._save_callback = save_callback
        self.model = AgentModel(self.session_id)
        self.model.bind_task(self.session_id, "AgentMain")
        self.tracker = Tracker()
        self.current_history = initial_history or []

        # 如果是彻头彻尾的全新初始化（没有任何历史），此时才 Build 最新规则
        if not self.current_history:
            fresh_prompt = self._build_system_prompt()
            self.current_history = [{"role": "system", "content": fresh_prompt}]
            # 注入跨会话共享短时缓存（独立消息，不污染 KV 首节点）
            if self.memo:
                memo_summary = json.dumps(self.memo, ensure_ascii=False, indent=2)
                self.current_history.append(
                    {
                        "role": "system",
                        "content": f"【系统通知：这是一个全新的会话。以下是系统在创建这个会话前的短时共享记忆缓存，或许对你有帮助】\n{memo_summary}",
                    }
                )

    def _build_system_prompt(self):
        soul_md, system_rules, memory_md = "", "", ""
        try:
            if os.path.exists(SOUL_MD_PATH):
                with open(SOUL_MD_PATH, "r", encoding="utf-8") as f:
                    soul_md = f.read().strip()
            if os.path.exists(SYSTEM_RULES_DIR):
                rule_files = sorted(
                    [f for f in os.listdir(SYSTEM_RULES_DIR) if f.endswith(".md")]
                )
                for rf in rule_files:
                    with open(
                        os.path.join(SYSTEM_RULES_DIR, rf), "r", encoding="utf-8"
                    ) as f:
                        system_rules += f.read().strip() + "\n\n"
                system_rules = system_rules.strip()
            if os.path.exists(MEMORY_MD_PATH):
                with open(MEMORY_MD_PATH, "r", encoding="utf-8") as f:
                    memory_md = f.read().strip()
        except Exception as e:
            print(f"⚠️ Prompt 构建发生异常: {e}")

        combined = soul_md
        if system_rules:
            combined += f"\n\n---\n\n{system_rules}"
        if memory_md:
            combined += f"\n\n---\n\n# 【系统长期记忆档案】\n\n{memory_md}"
        return combined

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

    def _get_tool_schema(self):
        return AGENT_TOOL_SCHEMA

    def _get_current_interaction_id(self):
        return self._interaction_id

    def _increment_interaction_id(self):
        self._interaction_id += 1
        return self._interaction_id

    def force_interrupt(self):
        print("🔒 [强制打断] 递增交互ID以隔离旧响应")
        self._increment_interaction_id()
        self.state = "idle"

    def get_history(self):
        return copy.deepcopy(self.current_history)

    def _append_history(self, message: dict):
        self.current_history.append(message)
        try:
            self.tracker.add(message)
            self.save_checkpoint()
        except Exception as e:
            print(f"⚠️ [Memory] 落盘失败: {e}")

    def force_push(self, content, type="user"):
        self.pending_force_push.append(
            {
                "type": type,
                "time": datetime.datetime.now().strftime("%m-%d %H:%M:%S"),
                "content": content,
            }
        )

    def _track_token_usage(self, response):
        if hasattr(response, "usage") and response.usage is not None:
            self.window_token = response.usage.total_tokens

    def _checker(self):
        local_push = []
        if self.pending_force_push:
            local_push = self.pending_force_push.copy()
            self.pending_force_push.clear()

        if local_push:
            batch_data = {"events": local_push}
            self._append_history(
                {"role": "user", "content": json.dumps(batch_data, ensure_ascii=False)}
            )

    def process_message(self):
        current_interaction_id = self._increment_interaction_id()
        self.force_push(
            content="任务开始前如有需要可以调用 Search 工具搜索本地相关的工具。完成任务后请调用 Memo 工具及时更新记忆，记录的记忆越多越详细以后你的能力就会越强",
            type="system",
        )

        while True:
            try:
                if self._get_current_interaction_id() != current_interaction_id:
                    print(
                        f"⚠️ [隔离] 检测到交互ID过期 ({current_interaction_id} != {self._get_current_interaction_id()})，丢弃旧响应"
                    )
                    break

                self._checker()
                safe_history = self.get_history()
                response = self.model.chat(
                    messages=safe_history, tools=self._get_tool_schema()
                )

                if self._get_current_interaction_id() != current_interaction_id:
                    print(
                        f"⚠️ [隔离] 网络响应返回后检测到交互ID过期 ({current_interaction_id} != {self._get_current_interaction_id()})，丢弃响应"
                    )
                    break
                self._track_token_usage(response)
                msg_resp = response.choices[0].message
                has_tools = self._process_assistant_message(msg_resp)
                if not has_tools:
                    print("✅ 消息处理闭环结束。")
                    break
                should_pause = self._execute_tool_calls(msg_resp.tool_calls)
                if should_pause:
                    break

            except KeyboardInterrupt:
                self._handle_interaction_error(is_interrupt=True)
                break
            except Exception as e:
                self._handle_interaction_error(e=e)
                break


    def _process_assistant_message(self, msg_resp) -> bool:
        assist_msg = {"role": "assistant", "content": msg_resp.content or ""}
        rc = getattr(msg_resp, "reasoning_content", None)
        if rc is None and hasattr(msg_resp, "model_dump"):
            rc = msg_resp.model_dump().get("reasoning_content")
        if rc is not None:
            assist_msg["reasoning_content"] = rc
        if msg_resp.tool_calls:
            assist_msg["tool_calls"] = [
                {
                    "id": t.id,
                    "type": t.type,
                    "function": {
                        "name": t.function.name,
                        "arguments": t.function.arguments,
                    },
                }
                for t in msg_resp.tool_calls
            ]
        self._append_history(assist_msg)
        if msg_resp.content:
            from src.sensor import send_to_sensors

            send_to_sensors(f"{msg_resp.content}")

    def _execute_tool_calls(self, tool_calls) -> bool:
        for tool_call in tool_calls:
            target_tool_name = tool_call.function.name
            arguments_str = tool_call.function.arguments
            arguments = {}
            if arguments_str:
                try:
                    arguments = json.loads(arguments_str)
                except Exception:
                    if repair_json:
                        arguments = repair_json(arguments_str, return_objects=True)
            if not isinstance(arguments, dict):
                error_msg = "❌ 系统拦截：工具参数格式严重损坏。"
                self._append_history(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": target_tool_name,
                        "content": error_msg,
                    }
                )
                continue
            if target_tool_name == "Bash":
                arguments["session_id"] = self.session_id
            args_str = str(arguments)

            current_iid = self._get_current_interaction_id()
            result_content = dispatch_tool(target_tool_name, arguments)

            if self._get_current_interaction_id() != current_iid:
                print(
                    f"⚠️ [拦截] 工具 {target_tool_name} 执行完毕，但检测到会话已切换或被打断，丢弃幽灵结果。"
                )
                continue

            try:
                snip = (
                    json.loads(result_content).get("snip", "")
                    if isinstance(json.loads(result_content), dict)
                    else ""
                )
            except Exception:
                snip = str(result_content)[:100]
            from src.sensor import send_to_sensors

            send_to_sensors(
                f"🔧{target_tool_name}({args_str[:50]}...)\n\n---\n\n{snip}"
            )
            self._append_history(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": target_tool_name,
                    "content": result_content,
                }
            )

            # ==== 在模型调用 Memo add 操作后，触发显性检查拦截 ====
            if target_tool_name == "Memo" and arguments.get("action") == "add":
                memo_data = arguments.get("memo_data")
                if memo_data:
                    self.memo.append(memo_data)
                    if len(self.memo) > 10:
                        self.memo = self.memo[-10:]
                    SessionStore.save_global_memo(self.memo)
                from src.utils.config import get_model_config

                model_cfg = get_model_config().get("main", {}).get(self.name, {})
                max_tokens = model_cfg.get("max_token", 500000)
                if self.window_token >= max_tokens:
                    self._truncate_memory_if_needed(force=True)
        return False

    def _handle_interaction_error(self, e=None, is_interrupt=False):
        content_msg = (
            "⚠️ [中断] 运行被强制中断。" if is_interrupt else f"❌ [错误] 交互断层: {e}"
        )
        print(content_msg)
        if (
            self.current_history
            and self.current_history[-1].get("role") == "assistant"
            and self.current_history[-1].get("tool_calls")
        ):
            self.current_history.pop()
        self._append_history({"role": "assistant", "content": content_msg})

    def sensor(self):
        print("🚀 Agent 后台主核已启动...")
        while not self._stop_event.is_set():
            try:
                if self.pending_force_push:
                    self.state = "handling"
                    self.process_message()
                self.state = "idle"
                time.sleep(0.5)
            except BaseException as e:
                print(f"❌ 主核异常已被安全拦截: {e}")
                self.state = "idle"
                time.sleep(1)

    def save_checkpoint(self):
        if self._save_callback:
            self._save_callback()

    def force_compress_memory(self):
        self._truncate_memory_if_needed(force=True)

    def _truncate_memory_if_needed(self, force=False):
        from src.utils.config import get_model_config

        model_cfg = get_model_config().get("main", {}).get(self.name, {})
        max_tokens = model_cfg.get("max_token", 500000)
        if not force and self.window_token < max_tokens:
            return
        print(f"🗜️ 触发记忆截断 (约 {self.window_token} tokens)...")
        try:
            original_len = len(self.current_history)
            split_idx = self._find_safe_truncation_index(original_len)
            final_summary = (
                json.dumps(self.memo, ensure_ascii=False, indent=2)
                if self.memo
                else "（暂无缓存记忆）"
            )
            self._rebuild_and_save_history(split_idx, original_len, final_summary)
        except Exception as e:
            print(f"❌ 记忆截断发生异常: {e}")

    def _find_safe_truncation_index(self, original_len: int) -> int:
        start_idx = 1
        keep_recent = 20
        split_idx = original_len - keep_recent
        if split_idx > start_idx:
            while split_idx > start_idx:
                curr_msg = self.current_history[split_idx]
                prev_msg = self.current_history[split_idx - 1]
                if curr_msg.get("role") == "tool":
                    split_idx -= 1
                    continue
                if prev_msg.get("role") == "assistant" and prev_msg.get("tool_calls"):
                    split_idx -= 1
                    continue
                break
        if split_idx < start_idx:
            split_idx = start_idx
        return split_idx

    def _rebuild_and_save_history(
        self, split_idx: int, original_len: int, final_summary: str
    ):
        original_system_msg = self.current_history[0]
        truncation_msg = {
            "role": "system",
            "content": f"【系统通知：因上下文超限，更早的历史对话已被系统截断。以下是最近五次的短时缓存，请你利用这些缓存无缝接续当前工作：】\n{final_summary}",
        }
        self.current_history = [
            original_system_msg,
            truncation_msg,
        ] + self.current_history[split_idx:original_len]
        for msg in self.current_history:
            if msg.get("role") == "assistant" and "reasoning_content" in msg:
                msg["reasoning_content"] = ""
        print("✅ Agent记忆清理完毕！已注入 self.memo 提示词")
        self.window_token = 0
        self.save_checkpoint()

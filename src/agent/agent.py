import copy
import datetime
import json
import os
import threading
import time

from json_repair import repair_json

from src.agent.hook_handler import HookHandler
from src.agent.session_store import SessionStore
from src.model import AgentModel
from src.tool import AGENT_TOOL_SCHEMA
from src.tool.utils.route import dispatch_tool
from src.utils.config import (
    BUFFER_DIR,
    get_agent_model,
)
from src.utils.tracker import Tracker


class Agent:
    def __init__(self, session_id, initial_history=None, name=None, save_callback=None, paradigm_path="src/agent/system_rules/PARADIGM.yaml"):
        self.name = name or get_agent_model()
        self.session_id = session_id
        # === 常驻内存记忆缓存 ===
        self.memo = SessionStore.load_global_memo()
        self._state = "idle"
        self._interaction_id = 0
        self.pending_force_push = []
        self.window_token = 0
        self._stop_event = threading.Event()
        self._history_lock = threading.RLock()
        self._push_lock = threading.RLock()
        self._save_callback = save_callback
        self.model = AgentModel(self.session_id)
        self.model.bind_task(self.session_id, "AgentMain")
        self.tracker = Tracker()
        self.current_history = initial_history or []
        self.hook_handler = HookHandler(paradigm_path)
        if not self.current_history:
            fresh_prompt = self._build_system_prompt()
            self.current_history = [{"role": "system", "content": fresh_prompt}]

    def dump_agent_state(self):
        with self._history_lock:
            return {
                "session_id": self.session_id,
                "current_history": self.current_history,
                "hook_handler_state": self.hook_handler.get_state()
            }

    def load_agent_state(self, state_dict):
        with self._history_lock:
            self.session_id = state_dict["session_id"]
            self.current_history = state_dict["current_history"]
            self.hook_handler.load_state(state_dict.get("hook_handler_state"))

    def _build_system_prompt(self):
        results = self.hook_handler.execute("on_build_system_prompt", agent=self, epoch=0)
        prompt_parts = [res["inject_prompt"] for res in results if res.get("inject_prompt")]
        return "\n\n---\n\n".join(prompt_parts)

    def _inject_hook_results(self, stage_name, epoch=0, **kwargs):
        """统一的钩子执行与历史记录注入封装，返回 True 表示全部成功"""
        results = self.hook_handler.execute(stage_name, agent=self, epoch=epoch, **kwargs)
        all_success = True
        for res in results:
            if not res.get("success"):
                all_success = False
            if res.get("inject_prompt"):
                hint_data = {"type": "workflow_hint", "content": res["inject_prompt"]}
                self._append_history({
                    "role": "user",
                    "content": json.dumps(hint_data, ensure_ascii=False)
                })
        return all_success

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
        print("[Lock] 递增交互ID以隔离旧响应")
        self._increment_interaction_id()
        self.state = "idle"

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
        file_uri = "file:///" + filepath.replace("\\", "/")
        return f"【输入超出字数3000字限制，已将请求内容落盘到 <{file_uri}> 里】"

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

    def _track_token_usage(self, response):
        if hasattr(response, "usage") and response.usage is not None:
            self.window_token = response.usage.total_tokens

    def _check_and_fix_toolchain(self):
        """
        检查工具链完整性（支持多工具调用）。
        如果检测到 assistant 发起了 tool_calls，但尚未获得全部 tool 的返回结果（例如被强行打断或报错），
        则撤回该轮的所有残缺 tool 消息，并修正/删除 assistant 消息。
        """
        if not self.current_history:
            return

        with self._history_lock:
            idx = len(self.current_history) - 1

            # 1. 往前找，跳过所有尾部的 tool 消息
            while idx >= 0 and self.current_history[idx].get("role") == "tool":
                idx -= 1

            # 2. 如果找到的上一条是 assistant 且带有 tool_calls
            if idx >= 0 and self.current_history[idx].get("role") == "assistant":
                assistant_msg = self.current_history[idx]
                if assistant_msg.get("tool_calls"):
                    requested_ids = set(tc["id"] for tc in assistant_msg["tool_calls"])
                    # tool messages 在 idx+1 到末尾
                    answered_ids = set(
                        msg.get("tool_call_id")
                        for msg in self.current_history[idx + 1 :]
                    )

                    # 发现不匹配！说明中断了！
                    if requested_ids != answered_ids:
                        print(
                            f"[Warn.ToolChain] 检测到未完成的多工具调用链 (请求: {len(requested_ids)}, 实际返回: {len(answered_ids)})，正在清理并撤回悬空节点..."
                        )

                        # A. 弹出后面的所有残缺 tool 消息
                        while len(self.current_history) > idx + 1:
                            self.current_history.pop()

                        # B. 如果 assistant 还有实质性的回复文本，保留文本，只摘除 tool_calls
                        if (
                            assistant_msg.get("content")
                            and str(assistant_msg.get("content")).strip()
                        ):
                            del assistant_msg["tool_calls"]
                        else:
                            # 否则这整条 assistant 消息都是多余的，直接弹出
                            self.current_history.pop()

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

    def process_message(self):
        current_interaction_id = self._increment_interaction_id()
        self._bg_search_task_id = current_interaction_id

        user_texts = [
            msg["content"]
            for msg in self.pending_force_push
            if msg.get("type") == "user"
        ]
        merged_input = " ".join(user_texts).strip()
        is_real_user_input = bool(merged_input)

        if is_real_user_input:
            self._inject_hook_results("on_loop_start", epoch=0)
            def background_hint_check(task_id):
                if getattr(self, "_bg_search_task_id", None) != task_id:
                    return

                try:
                    from src.tool.search.skill_search import search_skills
                    from src.tool.search.mcp_search import mcp_search
                    from src.memory.purrmemo.client import get_memory_client
                    import time

                    skill_res, _ = search_skills(merged_input, top_k=5)
                    mcp_res, _ = mcp_search(merged_input, max_results=5)

                    high_score_skills = len(
                        [s for s in skill_res if s.get("score", 0) >= 0.5]
                    )
                    high_score_mcps = len(
                        [m for m in mcp_res if m.get("score", 0) >= 0.5]
                    )
                    total_tools = high_score_skills + high_score_mcps

                    if getattr(self, "_bg_search_task_id", None) != task_id:
                        return

                    client = get_memory_client()
                    valid_memos = 0
                    if client.search_tool.vector_engine:
                        exps = client.search_tool.vector_engine.search_experiences(
                            merged_input, top_k=5
                        )
                        valid_exps = len(
                            [e for e in exps if e.get("score", 0.0) >= 0.5]
                        )

                        events = client.search_tool.vector_engine.search_events_vector(
                            merged_input, top_k=5
                        )
                        valid_events = len(
                            [e for e in events if e.get("score", 0.0) >= 0.5]
                        )

                        valid_memos = valid_exps + valid_events

                    if total_tools == 0 and valid_memos == 0:
                        return

                    time.sleep(10)

                    if (
                        getattr(self, "_bg_search_task_id", None) != task_id
                        or self.state != "handling"
                    ):
                        return

                    already_searched = False
                    already_memo_searched = False
                    with self._history_lock:
                        for msg in reversed(self.current_history):
                            if msg.get("role") == "user":
                                break
                            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                                for tc in msg.get("tool_calls"):
                                    func_name = tc.get("function", {}).get("name", "")
                                    args_str = tc.get("function", {}).get("arguments", "")
                                    if func_name == "Search" and any(r in args_str for r in ["local", "skill", "mcp"]):
                                        already_searched = True
                                    elif func_name == "Memo" and '"action":"search"' in args_str.replace(" ", ""):
                                        already_memo_searched = True

                    hints = []
                    if not already_searched and total_tools > 0:
                        hints.append(
                            f"检查到有 {total_tools} 条 skill/mcp 与本轮对话的总输入语义高度相关，可以尝试使用 Search 工具(route='local')检索相关数据。"
                        )
                    if not already_memo_searched and valid_memos > 0:
                        hints.append(
                            f"检查到记忆库中有 {valid_memos} 条经验/事件与本轮对话的总输入高度相关，可以尝试使用 Memo 工具(action='search')检索。"
                        )

                    if hints:
                        self.force_push("\n\n".join(hints), type="system")
                except Exception as e:
                    print(f"[Warn] 后台预搜索线程异常: {e}")

            threading.Thread(
                target=background_hint_check,
                args=(current_interaction_id,),
                daemon=True,
            ).start()

        used_tools = {}
        loop_epoch = 0
        while True:
            try:
                loop_epoch += 1
                self._inject_hook_results("on_loop_epoch", epoch=loop_epoch)
                if self._get_current_interaction_id() != current_interaction_id:
                    print(
                        f"[Warn.Session] 检测到交互ID过期 ({current_interaction_id} != {self._get_current_interaction_id()})，丢弃旧响应"
                    )
                    break

                self._checker()

                with self._history_lock:
                    safe_history = list(self.current_history)

                response = self.model.chat(messages=safe_history, tools=self._get_tool_schema())

                if self._get_current_interaction_id() != current_interaction_id:
                    print("[Warn.Session] 网络响应返回后检测到交互ID过期，丢弃响应")
                    break

                self._track_token_usage(response)
                msg_resp = response.choices[0].message
                has_tools = self._process_assistant_message(msg_resp)

                if msg_resp.tool_calls:
                    for t in msg_resp.tool_calls:
                        args_dict = {}
                        if t.function.arguments:
                            try:
                                args_dict = json.loads(t.function.arguments)
                            except Exception:
                                pass
                        used_tools.setdefault(t.function.name, []).append(args_dict)

                if has_tools:
                    should_pause = self._execute_tool_calls(msg_resp.tool_calls)
                    all_tool_success = self._inject_hook_results(
                        "on_tool_calling",
                        epoch=loop_epoch,
                        used_tools=used_tools
                    )
                    if not all_tool_success:
                        continue
                    if should_pause:
                        break
                else:
                    all_success = self._inject_hook_results(
                        "on_loop_end",
                        epoch=loop_epoch,
                        used_tools=used_tools
                    )
                    if all_success:
                        print("[Debug] 所有条件及拦截器检验通过，正常关闭循环。")
                        break
                    else:
                        hint_data = {"type": "workflow_hint", "content": "未满足结束循环条件，已自动打回"}
                        self._append_history({
                            "role": "user",
                            "content": json.dumps(hint_data, ensure_ascii=False)
                        })
                        print(f"[Debug] 当前第 {loop_epoch} 轮条件不足，被打回重新触发模型迭代。")
                        continue

            except KeyboardInterrupt:
                self._handle_interaction_error(is_interrupt=True)
                break
            except Exception as e:
                self._handle_interaction_error(e=e)
                break

        self.save_checkpoint()

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

        return bool(msg_resp.tool_calls)

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
                error_msg = "[Error] 系统拦截：工具参数格式严重损坏。"
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
                    f"[Warn.Interrupt] 工具 {target_tool_name} 执行完毕，但检测到会话已切换或被打断，丢弃幽灵结果。"
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
                    if len(self.memo) > 6:
                        self.memo = self.memo[-6:]
                    SessionStore.save_global_memo(self.memo)
                from src.utils.config import get_model_config

                model_cfg = get_model_config().get("main", {}).get(self.name, {})
                max_tokens = model_cfg.get("max_token", 500000)
                if self.window_token >= max_tokens:
                    self._truncate_memory_if_needed(force=True)
        return False

    def _handle_interaction_error(self, e=None, is_interrupt=False):
        content_msg = (
            "[Warn.Interrupt] 运行被强制中断。" if is_interrupt else f"[Error.Fault] 交互断层: {e}"
        )
        print(content_msg)

        self._check_and_fix_toolchain()

        self._append_history({"role": "assistant", "content": content_msg})

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
        self._truncate_memory_if_needed(force=True)

    def _truncate_memory_if_needed(self, force=False):
        from src.utils.config import get_model_config

        model_cfg = get_model_config().get("main", {}).get(self.name, {})
        max_tokens = model_cfg.get("max_token", 500000)
        if not force and self.window_token < max_tokens:
            return

        print(
            f"[Truncate] 触发记忆截断 (当前约 {self.window_token} tokens)，正在进入内部交互请求模型进行全局大总结..."
        )

        now_str = datetime.datetime.now().strftime("%m-%d %H:%M:%S")

        compression_prompt = {
            "role": "user",
            "content": json.dumps(
                {
                    "events": [
                        {
                            "type": "system",
                            "time": now_str,
                            "content": "记忆窗口已达上限，系统将要删除所有对话历史。为防止上下文断层，请对当前所有会话细节、历史、当前工作记忆与进度进行大总结，然后调用 Memo 工具（必须设置 action='add'）传入总结。系统将仅保留这份总结。",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        }

        with self._history_lock:
            temp_history = self.current_history.copy() + [compression_prompt]

        summary_text = None
        msg_resp = None
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            try:
                response = self.model.chat(
                    messages=temp_history, tools=self._get_tool_schema()
                )
                msg_resp = response.choices[0].message

                valid_memo_found = False

                if msg_resp.tool_calls:
                    for tc in msg_resp.tool_calls:
                        if tc.function.name == "Memo":
                            try:
                                args = json.loads(tc.function.arguments)
                                if args.get("action") == "add" and args.get(
                                    "memo_data"
                                ):
                                    summary_text = (
                                        json.dumps(
                                            args.get("memo_data"), ensure_ascii=False
                                        )
                                        if isinstance(args.get("memo_data"), dict)
                                        else str(args.get("memo_data"))
                                    )
                                    valid_memo_found = True
                                    break
                            except Exception as e:
                                print(f"[Warn] 解析 Memo 参数失败: {e}")

                if valid_memo_found:
                    break
                else:
                    warning_msg = f"【第{attempt}次警告】未使用Memo工具进行记忆总结(或 action 不为 'add')！请只调用 Memo 工具并将 action 设为 'add'，不要调用其他任何无关工具。"

                    warning_prompt = {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "events": [
                                    {
                                        "type": "system",
                                        "time": datetime.datetime.now().strftime(
                                            "%m-%d %H:%M:%S"
                                        ),
                                        "content": warning_msg,
                                    }
                                ]
                            },
                            ensure_ascii=False,
                        ),
                    }
                    temp_history.append(warning_prompt)
                    print(f"[Warn.MemCompress] {warning_msg}")

            except Exception as e:
                print(f"[Error] 记忆总结网络请求失败: {e}")
                break

        if not summary_text:
            if msg_resp and msg_resp.content:
                summary_text = msg_resp.content
            else:
                summary_text = "（模型未能成功生成有效总结，上下文已强行截断）"

        try:
            with self._history_lock:
                original_len = len(self.current_history)
                keep_recent = 10
                split_idx = original_len - keep_recent

                if split_idx > 1:
                    while split_idx > 1:
                        curr_msg = self.current_history[split_idx]
                        prev_msg = self.current_history[split_idx - 1]
                        if curr_msg.get("role") == "tool":
                            split_idx -= 1
                            continue
                        if prev_msg.get("role") == "assistant" and prev_msg.get(
                            "tool_calls"
                        ):
                            split_idx -= 1
                            continue
                        break
                if split_idx < 1:
                    split_idx = 1

                recent_messages = self.current_history[split_idx:original_len]

                fresh_system_content = self._build_system_prompt()
                new_system_msg = {"role": "system", "content": fresh_system_content}

                summary_msg = {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "events": [
                                {
                                    "type": "system",
                                    "time": datetime.datetime.now().strftime(
                                        "%m-%d %H:%M:%S"
                                    ),
                                    "content": f"【历史记忆大总结】\n{summary_text}",
                                }
                            ]
                        },
                        ensure_ascii=False,
                    ),
                }

                self.current_history = (
                    [new_system_msg] + recent_messages + [summary_msg]
                )

                for msg in self.current_history:
                    if msg.get("role") == "assistant" and "reasoning_content" in msg:
                        msg["reasoning_content"] = ""

            print("[Success] Agent 记忆大总结与安全截断完毕！")
            self.window_token = 0
            self.save_checkpoint()

        except Exception as e:
            print(f"[Error] 记忆重组发生严重异常: {e}")

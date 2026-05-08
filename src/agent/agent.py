import datetime
import os
import time
import json
import threading
import copy
from src.utils.tracker import Tracker
from src.model import AgentModel
from src.tool import AGENT_TOOL_SCHEMA
from src.tool.utils.route import dispatch_tool
from src.utils.config import get_agent_model, SOUL_MD_PATH, SYSTEM_RULES_DIR, AGENT_CORE_DIR
from json_repair import repair_json

MEMORY_MD_PATH = os.path.join(AGENT_CORE_DIR, "MEMORY.md")


class Agent:
    def __init__(self, session_id, initial_history=None, name=None, save_callback=None):
        self.name = name or get_agent_model()
        self.session_id = session_id

        # === 核心状态 ===
        self._state = "idle"
        self._interaction_id = 0  # 当前交互的唯一标识，用于防止旧请求污染新会话

        self.pending_force_push = []
        self.window_token = 0
        self._stop_event = threading.Event()
        self._history_lock = threading.Lock()
        self._save_callback = save_callback

        self.model = AgentModel(self.session_id)
        self.model.bind_task(self.session_id, "AgentMain")
        self.system_prompt = self._build_system_prompt()
        self.tracker = Tracker()

        self.current_history = initial_history or []
        if not self.current_history:
            self.current_history = [{"role": "system", "content": self.system_prompt}]
        elif self.current_history[0].get("role") == "system":
            self.current_history[0]["content"] = self.system_prompt

    def _build_system_prompt(self):
        soul_md, system_rules, memory_md = "", "", ""
        try:
            if os.path.exists(SOUL_MD_PATH):
                with open(SOUL_MD_PATH, "r", encoding="utf-8") as f: soul_md = f.read().strip()
            if os.path.exists(SYSTEM_RULES_DIR):
                rule_files = sorted([f for f in os.listdir(SYSTEM_RULES_DIR) if f.endswith(".md")])
                for rf in rule_files:
                    with open(os.path.join(SYSTEM_RULES_DIR, rf), "r", encoding="utf-8") as f:
                        system_rules += f.read().strip() + "\n\n"
                system_rules = system_rules.strip()
            if os.path.exists(MEMORY_MD_PATH):
                with open(MEMORY_MD_PATH, "r", encoding="utf-8") as f: memory_md = f.read().strip()
        except Exception as e:
            print(f"⚠️ Prompt 构建发生异常: {e}")

        combined = soul_md
        if system_rules: combined += f"\n\n---\n\n{system_rules}"
        if memory_md: combined += f"\n\n---\n\n# 【系统长期记忆档案】\n\n{memory_md}"
        return combined

    def stop(self):
        self._stop_event.set()
        if hasattr(self, 'model') and self.model:
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
        """获取当前交互ID，用于验证响应是否属于当前会话"""
        return self._interaction_id

    def _increment_interaction_id(self):
        """递增交互ID，用于标记新的交互开始"""
        self._interaction_id += 1
        return self._interaction_id

    def force_interrupt(self):
        """强制打断当前交互，使旧线程的响应失效"""
        print("🔒 [强制打断] 递增交互ID以隔离旧响应")
        self._increment_interaction_id()
        self.state = "idle"

    def get_history(self):
        """提供给前端的安全读取接口"""
        return copy.deepcopy(self.current_history)

    def _append_history(self, message: dict):
        """安全写入历史"""
        self.current_history.append(message)
        try:
            self.tracker.add(message)
            self.save_checkpoint()
        except Exception as e:
            print(f"⚠️ [Memory] 落盘失败: {e}")

    def force_push(self, content, type="unknown_type"):
        """接收外部消息"""
        self.pending_force_push.append(f"<{type}>{content}</{type}>")

    def _track_token_usage(self, response):
        if hasattr(response, "usage") and response.usage is not None:
            self.window_token = response.usage.total_tokens

    def _checker(self):
        """提取排队消息合并入历史"""
        local_push = []
        if self.pending_force_push:
            local_push = self.pending_force_push.copy()
            self.pending_force_push.clear()

        if self.window_token > 0:
            self._check_and_summarize_memory()

        if local_push:
            formatted = "\n\n".join(local_push)
            self._append_history({
                "role": "user",
                "content": f"[SYSTEM {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Received {len(local_push)} message:\n\n{formatted}"
            })

    def process_message(self):
        """主 ReAct 循环"""
        # 获取当前交互ID，用于后续验证响应是否属于当前会话
        current_interaction_id = self._increment_interaction_id()
        while True:
            try:
                # 检查交互ID是否已过期（会话已被切换）
                if self._get_current_interaction_id() != current_interaction_id:
                    print(f"⚠️ [隔离] 检测到交互ID过期 ({current_interaction_id} != {self._get_current_interaction_id()})，丢弃旧响应")
                    break

                self._checker()
                # 传入隔离后的历史记录副本进行请求，防止请求中被并发修改
                safe_history = self.get_history()
                response = self.model.chat(messages=safe_history, tools=self._get_tool_schema())
                
                # 再次检查交互ID，因为网络请求可能耗时较长，期间会话可能已切换
                if self._get_current_interaction_id() != current_interaction_id:
                    print(f"⚠️ [隔离] 网络响应返回后检测到交互ID过期 ({current_interaction_id} != {self._get_current_interaction_id()})，丢弃响应")
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

        try:
            self._check_and_summarize_memory()
        except Exception as e:
            print(f"⚠️ 压缩记忆失败：{e}")

    def _process_assistant_message(self, msg_resp) -> bool:
        assist_msg = {"role": "assistant", "content": msg_resp.content or ""}
        rc = getattr(msg_resp, "reasoning_content", None)
        if rc is None and hasattr(msg_resp, "model_dump"):
            rc = msg_resp.model_dump().get("reasoning_content")

        if rc is not None: assist_msg["reasoning_content"] = rc

        if msg_resp.tool_calls:
            assist_msg["tool_calls"] = [
                {"id": t.id, "type": t.type, "function": {"name": t.function.name, "arguments": t.function.arguments}}
                for t in msg_resp.tool_calls
            ]
        self._append_history(assist_msg)

        if rc: print(f"🧠 模型深度思考:\n{rc}\n")
        if msg_resp.content:
            from src.sensor import get_gateway
            get_gateway().send(f"{msg_resp.content}")

        return bool(msg_resp.tool_calls)

    def _execute_tool_calls(self, tool_calls) -> bool:
        for tool_call in tool_calls:
            target_tool_name = tool_call.function.name
            arguments_str = tool_call.function.arguments
            arguments = {}

            if arguments_str:
                try:
                    arguments = json.loads(arguments_str)
                except Exception as e:
                    if repair_json: arguments = repair_json(arguments_str, return_objects=True)

            if not isinstance(arguments, dict):
                error_msg = "❌ 系统拦截：工具参数格式严重损坏。"
                self._append_history(
                    {"role": "tool", "tool_call_id": tool_call.id, "name": target_tool_name, "content": error_msg})
                continue

            if target_tool_name in ["execute_command", "close_shell", "Bash"]:
                arguments["session_id"] = self.session_id

            args_str = str(arguments)
            from src.sensor import get_gateway

            result_content = dispatch_tool(target_tool_name, arguments)
            try:
                snip = json.loads(result_content).get('snip', '') if isinstance(json.loads(result_content),
                                                                                dict) else ''
            except:
                snip = str(result_content)[:100]

            get_gateway().send(f"🔧{target_tool_name}({args_str[:50]}...)\n\n---\n\n{snip}")
            self._append_history(
                {"role": "tool", "tool_call_id": tool_call.id, "name": target_tool_name, "content": result_content})

        return False

    def _handle_interaction_error(self, e=None, is_interrupt=False):
        content_msg = "⚠️ [中断] 运行被强制中断。" if is_interrupt else f"❌ [错误] 交互断层: {e}"
        print(content_msg)

        if self.current_history and self.current_history[-1].get("role") == "assistant" and self.current_history[
            -1].get("tool_calls"):
            self.current_history.pop()

        self._append_history({"role": "assistant", "content": content_msg})


    def sensor(self):
        print("🚀 Agent 后台主核已启动...")
        while not self._stop_event.is_set():
            try:
                has_pending = False
                if self.pending_force_push:
                    has_pending = True

                if has_pending:
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


    def _check_and_summarize_memory(self, check_mode=True):
        from src.utils.config import get_model_config, get_agent_model
        agent_name = get_agent_model()
        model_cfg = get_model_config().get("main", {}).get(agent_name, {})
        max_tokens = model_cfg.get("max_token", 500000)
        if check_mode and self.window_token < max_tokens:
            return

        print(f"🗜️ 记忆容量到达 {len(self.current_history)} 条 (约 {self.window_token} tokens)，触发自我归档...")

        try:
            # 1. 准备沙箱环境
            alert_prompt = """【系统警告：记忆容量即将溢出，触发自动记忆归档】
为了防止对话断层，系统即将清理你最早期的一批记忆。
你必须调用 `Memo` 工具将当前记忆进行分类归档：
- short_term: （必填）短期工作记忆。对当前任务的上下文进行压缩，该项将在清理后直接返回到你的新对话中，以便你继续当前工作。
- work_exp: （列表）工作中积累的经验教训。<有则必须填写>
- user_profile: （列表）对用户的新认识，包括但不限于喜好、风格等。<有则必须填写>
- events: （列表）最近发生的事件，大大小小越多越好。格式：[{"time":"20200601","event":"xxx"}]。<有则必须填写>
- cognition: （列表）对世界的新认知，提取具有普适性的概念或规律。<有则必须填写>
注意：这些分类的内容可以重叠并鼓励重叠（比如一件事既是 event，也反映了 user_profile）。请直接调用工具即可，无须输出废话。"""
            temp_history = self.current_history.copy()
            temp_history.append({"role": "user", "content": alert_prompt})

            # 2. 在沙箱中执行归档提取
            archive_success, final_summary = self._run_memory_archive_loop(temp_history)

            # 3. 寻找安全的截断点（避开未闭环的 tool_call）
            original_len = len(self.current_history)
            split_idx = self._find_safe_truncation_index(original_len)

            # 4. 重构主历史记录并落盘
            self._rebuild_and_save_history(split_idx, original_len, final_summary)

        except Exception as e:
            print(f"❌ 记忆存档发生异常: {e}")

    def _run_memory_archive_loop(self, temp_history) -> tuple[bool, str]:
        """在沙箱中运行归档循环，处理工具调用与异常重试"""
        current_tools = AGENT_TOOL_SCHEMA
        max_retries = 3
        archive_success = False
        archived_contents = []

        for _ in range(max_retries):
            response = self.model.chat(messages=temp_history, tools=current_tools)
            msg_resp = response.choices[0].message
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
                        "function": {"name": t.function.name, "arguments": t.function.arguments}
                    } for t in msg_resp.tool_calls
                ]
                temp_history.append(assist_msg)
                has_update_memo = False

                for t in msg_resp.tool_calls:
                    if t.function.name == "Memo":
                        has_update_memo = True
                        try:
                            args_str = t.function.arguments
                            args = {}
                            if args_str:
                                try:
                                    args = json.loads(args_str)
                                except json.JSONDecodeError as e:
                                    print(f"⚠️ Memo JSON 解析失败，尝试修复: {e}")
                                    if repair_json:
                                        args = repair_json(args_str, return_objects=True)

                            if isinstance(args, dict):
                                # Call Memo and check result
                                from src.utils.config import get_model_config
                                model_cfg = get_model_config().get("main", {}).get(self.name, {})
                                max_tokens = model_cfg.get("max_token", 500000)
                                remaining = max_tokens - self.window_token
                                tool_result = dispatch_tool("Memo", args, available_tokens=remaining)
                                import json
                                try:
                                    result_data = json.loads(tool_result)
                                    is_error = result_data.get("type") == "error"
                                except Exception:
                                    is_error = "❌" in str(tool_result) or "error" in str(tool_result).lower()

                                if is_error:
                                    # Validation failed - send back to agent for retry
                                    error_msg = str(tool_result)[:300]
                                    tool_response = f'❌ 参数格式错误，请修正后重试: {error_msg}'
                                    has_update_memo = False  # Don't break, let agent retry
                                else:
                                    param_parts = []
                                    for key, val in args.items():
                                        val_str = json.dumps(val, ensure_ascii=False) if isinstance(val, (dict, list)) else str(val)
                                        param_parts.append(f"  - **{key}**: {val_str}")
                                    if param_parts:
                                        archived_contents.append("\n".join(param_parts))
                                    tool_response = '✅ 归档工具调用成功'
                        except Exception as e:
                            print(f"⚠️ Memo 执行异常: {e}")
                            try:
                                fallback_args = repair_json(t.function.arguments,
                                                            return_objects=True) if repair_json else json.loads(
                                    t.function.arguments)
                                if isinstance(fallback_args, dict):
                                    param_parts = [f"  - **{k}**: {v}" for k, v in fallback_args.items()]
                                    archived_contents.append("\n".join(param_parts))
                                else:
                                    archived_contents.append(str(t.function.arguments))
                            except:
                                archived_contents.append(str(t.function.arguments))
                            tool_response = f'⚠️ Memo 执行异常但已记录: {str(e)[:100]}'

                        temp_history.append({
                            "role": "tool",
                            "tool_call_id": t.id,
                            "name": t.function.name,
                            "content": tool_response
                        })
                    else:
                        temp_history.append({
                            "role": "tool",
                            "tool_call_id": t.id,
                            "name": t.function.name,
                            "content": '❌ 系统拦截：当前处于强制归档阶段，请立刻调用 Memo。'
                        })

                if has_update_memo:
                    archive_success = True
                    print("🧠 Agent归档完成，成功处理 Memo 调用。")
                    break
                else:
                    temp_history.append({"role": "user", "content": "打回：你必须调用 `Memo` 工具来归档备忘录！"})
            else:
                temp_history.append(assist_msg)
                temp_history.append(
                    {"role": "user", "content": "打回：你必须调用 `Memo` 工具！请不要只回复纯文本。"})

        if archive_success:
            final_summary = "\n\n".join(archived_contents) if archived_contents else "（无归档细节）"
        else:
            print("⚠️ 未能成功调用 Memo 工具，强制截断可能导致上下文丢失。")
            final_summary = "未保存成功的早期上下文片段..."

        return archive_success, final_summary

    def _find_safe_truncation_index(self, original_len: int) -> int:
        """寻找安全的截断点，避开未闭环的 Tool Call"""
        start_idx = 1
        keep_recent = 20
        split_idx = original_len - keep_recent

        if split_idx > start_idx:
            while split_idx > start_idx:
                curr_msg = self.current_history[split_idx]
                prev_msg = self.current_history[split_idx - 1]
                # 避开切碎 tool 结果
                if curr_msg.get("role") == "tool":
                    split_idx -= 1
                    continue
                # 避开切碎 assistant 刚刚发起的 tool_call
                if prev_msg.get("role") == "assistant" and prev_msg.get("tool_calls"):
                    split_idx -= 1
                    continue
                break

        if split_idx < start_idx:
            split_idx = start_idx

        return split_idx

    def _rebuild_and_save_history(self, split_idx: int, original_len: int, final_summary: str):
        """重构主历史流并完成持久化"""
        system_msg = {"role": "system", "content": self._build_system_prompt()}
        summary_msg = {"role": "assistant", "content": f"【系统已截断历史，以下是刚刚生成的归档记录与工作缓存】\n{final_summary}"}
        if any("reasoning_content" in msg for msg in self.current_history if msg.get("role") == "assistant"):
            summary_msg["reasoning_content"] = ""
        self.current_history = [system_msg] + self.current_history[split_idx:original_len] + [summary_msg]
        self.system_prompt = self._build_system_prompt()
        self.current_history[0]["content"] = self.system_prompt
        print("✅ Agent记忆清理完毕！归档过程已在沙箱中隐蔽完成，主历史流保持纯净。")
        self.window_token = 0
        self.save_checkpoint()

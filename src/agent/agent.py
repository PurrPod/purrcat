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
from src.agent.session_store import SessionStore

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
                self.current_history.append({
                    "role": "system",
                    "content": f"【系统通知：这是一个全新的会话。以下是系统在创建这个会话前的短时共享记忆缓存，或许对你有帮助】\n{memo_summary}"
                })

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
        self.pending_force_push.append({
            "type": type,
            "time": datetime.datetime.now().strftime('%m-%d %H:%M:%S'),
            "content": content
        })

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
            self._append_history({
                "role": "user",
                "content": json.dumps(batch_data, ensure_ascii=False)
            })

    def _sanitize_history(self, history: list) -> list:
            """深度清洗历史记录，完美处理多工具并发、断层、幽灵消息问题"""
            import copy
            
            sanitized = []
            # 记录期望收到结果的工具：{tool_call_id: 对应的 assistant 消息在 sanitized 中的索引}
            pending_tool_calls = {}  

            # 必须深拷贝，避免清洗过程污染原始的 current_history
            working_history = copy.deepcopy(history)

            for msg in working_history:
                role = msg.get("role")

                if role == "assistant":
                    sanitized.append(msg)
                    if msg.get("tool_calls"):
                        # 并发场景：记录下这个 assistant 发出的所有 tool_call_id
                        for tc in msg.get("tool_calls"):
                            pending_tool_calls[tc["id"]] = len(sanitized) - 1
                            
                elif role == "tool":
                    tc_id = msg.get("tool_call_id")
                    if tc_id in pending_tool_calls:
                        # 这是合法并发工具调用之一，放行
                        sanitized.append(msg)
                        # 收到结果，从待处理清单中划掉
                        del pending_tool_calls[tc_id]
                    else:
                        # 不在 pending 列表里的，绝对是跨会话残留的幽灵或重复数据，精准拦截
                        print(f"🧹 [清洗] 丢弃跨会话遗留的孤儿工具结果: {msg.get('name', 'unknown')} ({tc_id})")
                else:
                    sanitized.append(msg)

            # ==== 终极兜底：清理发出去但没收回来的“太监” tool_calls ====
            # 场景：大模型并发了 3 个工具，跑了 1 个后被用户切走，后 2 个被拦截。
            # 此时发给 API 会报 400（期待 3 个结果只给了 1 个）。必须把没结果的调用抹掉！
            if pending_tool_calls:
                print(f"🧹 [清洗] 移除未收到结果的断层 tool_calls: {list(pending_tool_calls.keys())}")
                
                # 按索引回溯，清理对应的 assistant 消息
                for tc_id, idx in pending_tool_calls.items():
                    ast_msg = sanitized[idx]
                    if "tool_calls" in ast_msg:
                        # 剔除掉那些因为中断而永远等不到结果的 tool_call
                        ast_msg["tool_calls"] = [tc for tc in ast_msg["tool_calls"] if tc["id"] != tc_id]
                        
                        # 如果并发的工具全军覆没被剔除了，把键也删了
                        if not ast_msg["tool_calls"]:
                            del ast_msg["tool_calls"]
                            # 如果这只是一条纯发起工具的消息，现在被掏空了，给个兜底文本防报错
                            if not ast_msg.get("content"):
                                ast_msg["content"] = "（任务执行被系统中断）"

            return sanitized

    def _sanitize_tail(self):
        """极致性能版：只在每次新任务开始时，检查并修复历史记录的'尾部'断层，耗时几乎为 0"""
        if not self.current_history:
            return

        last_ast_idx = -1
        for i in range(len(self.current_history) - 1, -1, -1):
            if self.current_history[i].get("role") == "assistant":
                last_ast_idx = i
                break

        if last_ast_idx == -1:
            return

        last_ast = self.current_history[last_ast_idx]
        if not last_ast.get("tool_calls"):
            return

        collected_tool_ids = {
            msg.get("tool_call_id")
            for msg in self.current_history[last_ast_idx + 1:]
            if msg.get("role") == "tool"
        }

        original_tc_count = len(last_ast["tool_calls"])
        valid_tcs = [tc for tc in last_ast["tool_calls"] if tc["id"] in collected_tool_ids]

        if len(valid_tcs) != original_tc_count:
            print(f"🧹 [尾部清理] 剔除 {original_tc_count - len(valid_tcs)} 个因中断而未完成的 tool_call")
            if valid_tcs:
                last_ast["tool_calls"] = valid_tcs
            else:
                del last_ast["tool_calls"]
                if not last_ast.get("content"):
                    last_ast["content"] = "（任务执行被系统中断）"

    def process_message(self):
        current_interaction_id = self._increment_interaction_id()
        self.force_push(
            content="任务开始前如有需要可以调用 Memo 工具搜索相关记忆。完成任务后请调用 Memo 工具及时更新记忆",
            type="system")

        self._sanitize_tail()

        while True:
            try:
                if self._get_current_interaction_id() != current_interaction_id:
                    print(f"⚠️ [隔离] 检测到交互ID过期 ({current_interaction_id} != {self._get_current_interaction_id()})，丢弃旧响应")
                    break

                self._checker()
                safe_history = self.get_history()
                response = self.model.chat(messages=safe_history, tools=self._get_tool_schema())

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

            current_iid = self._get_current_interaction_id()

            result_content = dispatch_tool(target_tool_name, arguments)

            if self._get_current_interaction_id() != current_iid:
                print(f"⚠️ [拦截] 工具 {target_tool_name} 执行完毕，但检测到会话已切换或被打断，丢弃幽灵结果。")
                continue

            try:
                snip = json.loads(result_content).get('snip', '') if isinstance(json.loads(result_content),
                                                                                dict) else ''
            except:
                snip = str(result_content)[:100]
            get_gateway().send(f"🔧{target_tool_name}({args_str[:50]}...)\n\n---\n\n{snip}")
            self._append_history(
                {"role": "tool", "tool_call_id": tool_call.id, "name": target_tool_name, "content": result_content})
            # ==== 在模型调用 Memo add 操作后，触发显性检查拦截 ====
            if target_tool_name == "Memo" and arguments.get("action") == "add":
                memo_data = arguments.get("memo_data")
                if memo_data:
                    self.memo.append(memo_data)
                    if len(self.memo) > 10:
                        self.memo = self.memo[-10:]
                    SessionStore.save_global_memo(self.memo)
                # 模型完成存档操作后，立刻检查是否超出阈值截断
                from src.utils.config import get_model_config
                model_cfg = get_model_config().get("main", {}).get(self.name, {})
                max_tokens = model_cfg.get("max_token", 500000)
                if self.window_token >= max_tokens:
                    self._truncate_memory_if_needed(force=True)
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
        """提供给外部/用户的显性触发接口"""
        self._truncate_memory_if_needed(force=True)

    def _truncate_memory_if_needed(self, force=False):
        """判断与执行截断的核心操作"""
        from src.utils.config import get_model_config
        model_cfg = get_model_config().get("main", {}).get(self.name, {})
        max_tokens = model_cfg.get("max_token", 500000)
        if not force and self.window_token < max_tokens:
            return
        print(f"🗜️ 触发记忆截断 (约 {self.window_token} tokens)...")
        try:
            original_len = len(self.current_history)
            split_idx = self._find_safe_truncation_index(original_len)
            final_summary = json.dumps(self.memo, ensure_ascii=False, indent=2) if self.memo else "（暂无缓存记忆）"
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

    def _rebuild_and_save_history(self, split_idx: int, original_len: int, final_summary: str):
        """重构主历史流并完成持久化：绝对保留原版 system 以命中 KV Cache，追加 memo 通知"""
        # 1. 提取首节点以保护 KV Cache
        original_system_msg = self.current_history[0]
        # 2. 准备短时缓存通知
        truncation_msg = {
            "role": "system",
            "content": f"【系统通知：因上下文超限，更早的历史对话已被系统截断。以下是最近五次的短时缓存，请你利用这些缓存无缝接续当前工作：】\n{final_summary}"
        }
        # 3. 先拼接！直接丢弃无需保留的旧消息
        self.current_history = [original_system_msg, truncation_msg] + self.current_history[split_idx:original_len]
        # 4. 后遍历！只对保留下来的“幸存者”清空庞大的思考过程，释放 Token 空间
        for msg in self.current_history:
            if msg.get("role") == "assistant" and "reasoning_content" in msg:
                msg["reasoning_content"] = ""
        print("✅ Agent记忆清理完毕！原系统指令保持不变以命中缓存，已注入 self.memo 提示词，并剥离旧有思考负担。")
        self.window_token = 0
        self.save_checkpoint()
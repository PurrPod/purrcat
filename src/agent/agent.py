import datetime
import os
import time
import json
import threading
import uuid
from src.loader.memory import Memory
from src.model.model import Model
from src.plugins.plugin_manager import parse_tool

from src.plugins.route.agent_tool import AGENT_TOOLS
from src.plugins.route.base_tool import BASE_TOOLS
from src.utils.config import (
    get_agent_model, SOUL_MD_PATH, SYSTEM_RULES_DIR, CHECKPOINT_PATH, TOOL_INDEX_FILE
)

from json_repair import repair_json

PRIORITY_MAP = {
    "owner_message": 100,
    "project_message": 80,
    "schedule": 60,
    "rss_update": 40,
    "heartbeat": 20
}

ROOT = False

MEMORY_MD_PATH = "src/agent/core/memory.md"


class Agent:
    def __init__(self, name=None, checkpoint_path=None):
        if not name:
            name = get_agent_model()
        self.name = name
        self.state = "idle"
        self.model = Model(self.name)
        self.agent_session_id = f"agent_main_{uuid.uuid4().hex[:8]}"
        self.model.bind_task(self.agent_session_id, "AgentMain")
        self.system_prompt = self._build_system_prompt()
        self.current_history = [{"role": "system", "content": self.system_prompt}]
        self.memory = Memory()
        self.checkpoint_path = checkpoint_path or CHECKPOINT_PATH
        self.pending_force_push = []
        self._lock = threading.Lock()
        self.window_token = 0
        self._stop_event = threading.Event()
    def _build_system_prompt(self):
        soul_md = ""
        try:
            if os.path.exists(SOUL_MD_PATH):
                with open(SOUL_MD_PATH, "r", encoding="utf-8") as f:
                    soul_md = f.read().strip()
        except Exception as e:
            print(f"⚠️ 读取 SOUL.md 失败: {e}")
        system_rules = ""
        try:
            if os.path.exists(SYSTEM_RULES_DIR):
                rule_files = sorted([
                    f for f in os.listdir(SYSTEM_RULES_DIR)
                    if f.endswith(".md")
                ])
                for rf in rule_files:
                    filepath = os.path.join(SYSTEM_RULES_DIR, rf)
                    with open(filepath, "r", encoding="utf-8") as f:
                        system_rules += f.read().strip() + "\n\n"
                system_rules = system_rules.strip()
        except Exception as e:
            print(f"⚠️ 读取 system_rules 目录失败: {e}")
        memory_md = ""
        try:
            if os.path.exists(MEMORY_MD_PATH):
                with open(MEMORY_MD_PATH, "r", encoding="utf-8") as f:
                    memory_md = f.read().strip()
        except Exception as e:
            print(f"⚠️ 读取 memory.md 失败: {e}")
        combined_prompt = soul_md
        if system_rules:
            combined_prompt += f"\n\n---\n\n{system_rules}"
        if memory_md:
            combined_prompt += f"\n\n---\n\n# 【系统长期记忆档案】\n\n{memory_md}"
        return combined_prompt

    def stop(self):
        self._stop_event.set()

    def _append_history(self, message: dict):
        self.current_history.append(message)
        try:
            self.memory.add(message)
            self.save_checkpoint()
        except Exception as e:
            print(f"⚠️ [Memory] 落盘失败: {e}")

    def force_push(self, content, type="unknown_type"):
        with self._lock:
            self.pending_force_push.append(f"<{type}>{content}</{type}>")

    def _track_token_usage(self, response):
        """精准统计 API Token，防止重复累加"""
        if hasattr(response, "usage") and response.usage is not None:
            self.window_token = response.usage.total_tokens

    def _checker(self):
        local_push = []
        with self._lock:
            if self.pending_force_push:
                local_push = self.pending_force_push.copy()
                self.pending_force_push.clear()
        if self.window_token > 0:
            self._check_and_summarize_memory()
        if local_push:
            len_messages = len(local_push)
            formatted_messages = "\n\n".join(local_push)
            self._append_history({
                "role": "user",
                "content": f"[System] You receive {len_messages} message:\n\n{formatted_messages}"
            })
    def process_message(self):
        """核心 ReAct 交互循环 (主调度器)"""
        self.state = "handling"
        while True:
            try:
                # 1. 检查并强制推入被挂起的消息
                self._checker()

                # 2. 与大模型交互，获取回复
                msg_resp = self._step_model_interaction()

                # 3. 解析助手消息并落盘
                has_tools = self._process_assistant_message(msg_resp)

                # 4. 判断闭环：如果没有工具调用，本轮思考结束
                if not has_tools:
                    print("✅ 消息处理闭环结束。")
                    self.state = "idle"
                    break

                # 5. 执行工具链
                should_pause = self._execute_tool_calls(msg_resp.tool_calls)
                if should_pause:
                    # 遭遇 __AGENT_PAUSE__，直接中断当前处理流
                    self.state = "idle"
                    return

            except KeyboardInterrupt:
                self._handle_interaction_error(is_interrupt=True)
                raise
            except Exception as e:
                self._handle_interaction_error(e=e)
                break

        try:
            self._check_and_summarize_memory()
        except Exception as e:
            print(f"压缩记忆失败：{e}")

    def _step_model_interaction(self):
        """封装与大模型的 API 请求，并统计 Token"""
        current_tools = list(BASE_TOOLS) + list(AGENT_TOOLS)
        response = self.model.chat(messages=self.current_history, tools=current_tools)
        self._track_token_usage(response)
        return response.choices[0].message

    def _process_assistant_message(self, msg_resp) -> bool:
        """解析助手的回复内容，组装历史并打印。返回是否包含工具调用"""
        assist_msg = {"role": "assistant", "content": msg_resp.content or ""}

        # 兼容读取 reasoning_content (思考模型支持)
        rc = getattr(msg_resp, "reasoning_content", None)
        if rc is None and hasattr(msg_resp, "model_dump"):
            rc = msg_resp.model_dump().get("reasoning_content")

        if rc is not None:
            assist_msg["reasoning_content"] = rc

        # 组装工具调用记录
        if msg_resp.tool_calls:
            assist_msg["tool_calls"] = [
                {
                    "id": t.id,
                    "type": t.type,
                    "function": {"name": t.function.name, "arguments": t.function.arguments}
                } for t in msg_resp.tool_calls
            ]

        self._append_history(assist_msg)

        # 控制台打印输出
        if rc:
            print(f"🧠 模型深度思考:\n{rc}\n")
        if msg_resp.content:
            print(f"🤖 助手回复: {msg_resp.content}")

        return bool(msg_resp.tool_calls)

    def _execute_tool_calls(self, tool_calls) -> bool:
        """执行工具调用链。如果任务被挂起返回 True，否则返回 False 继续循环"""
        for idx, tool_call in enumerate(tool_calls):
            original_tool_name = tool_call.function.name
            target_tool_name = original_tool_name
            arguments_str = tool_call.function.arguments
            arguments = {}

            # --- 1. 参数解析与 json-repair 容错 ---
            if arguments_str:
                try:
                    arguments = json.loads(arguments_str)
                except json.JSONDecodeError as e:
                    print(f"⚠️ 标准 JSON 解析失败，尝试容错修复: {e}")
                    if repair_json:
                        try:
                            arguments = repair_json(arguments_str, return_objects=True)
                            print("✅ json-repair 修复成功！")
                        except Exception as repair_e:
                            print(f"❌ json-repair 修复失败: {repair_e}")

            # --- 2. 代理工具无缝拆包拦截 ---
            if original_tool_name == "call_dynamic_tool" and isinstance(arguments, dict):
                target_tool_name = arguments.get("target_tool_name", "")
                target_args = arguments.get("arguments", {})
                if isinstance(target_args, str):
                    try:
                        arguments = json.loads(target_args)
                    except Exception:
                        if repair_json:
                            try:
                                arguments = repair_json(target_args, return_objects=True)
                            except:
                                arguments = target_args
                else:
                    arguments = target_args

            # --- 3. 拦截损坏参数 ---
            if not isinstance(arguments, dict):
                error_msg = "❌ 系统拦截：工具参数格式严重损坏。可能是由于命令过长导致的截断或转义错误，建议分批运行指令！！！"
                print(error_msg)
                self._append_history({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": original_tool_name,
                    "content": error_msg
                })
                continue

            # --- 4. 环境参数注入 ---
            if target_tool_name in ["execute_command", "close_shell"]:
                arguments["session_id"] = self.agent_session_id

            # --- 5. 执行与挂起逻辑 ---
            args_str = ", ".join([f'{k}={repr(v)}' for k, v in arguments.items()]) if isinstance(arguments,
                                                                                                 dict) else str(
                arguments)
            print(f"🔧 助手调起工具: {target_tool_name}({args_str})")

            result_str = parse_tool(target_tool_name, arguments)
            finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if result_str == "__AGENT_PAUSE__":
                print("⏸️ Agent 已将当前任务放入挂起表，准备处理下一条消息...")
                time_aware_content = f"[finish at {finish_time}]\n工具调用成功，正在挂起任务，请耐心等待处理"
                self._append_history({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": original_tool_name,
                    "content": time_aware_content
                })

                # 废弃后续所有未执行的工具
                remaining_tools = tool_calls[idx + 1:]
                for rem_tool in remaining_tools:
                    self._append_history({
                        "role": "tool",
                        "tool_call_id": rem_tool.id,
                        "name": rem_tool.function.name,
                        "content": "任务已被挂起，当前工具执行跳过。"
                    })
                return True  # 返回 True 通知主循环中断当前流

            # --- 6. 正常工具回传 ---
            print(f"📦 工具回传结果: {result_str}")
            time_aware_content = f"[finish at {finish_time}]\n{result_str}"
            self.current_history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": original_tool_name,
                "content": time_aware_content
            })

        return False  # 正常执行完毕，继续 ReAct 循环

    def _handle_interaction_error(self, e=None, is_interrupt=False):
        """统一处理大模型交互中的异常与撤销现场保护"""
        self.state = "idle"

        if is_interrupt:
            print("⚠️ [Agent] 检测到强制中断 (Ctrl+C)，保存现场...")
            content_msg = "⚠️ [系统提示] Agent 运行被用户或系统强制中断 (Ctrl+C)。"
        else:
            print(f"❌ [Agent] 大模型交互断层: {e}")
            content_msg = f"❌ [系统报错] Agent 遭遇意外交互断层，当前处理已终止。错误信息：{e}"

        # 撤销未闭环的 tool_calls
        if self.current_history and self.current_history[-1].get("role") == "assistant" and self.current_history[
            -1].get("tool_calls"):
            self.current_history.pop()
            print("⚠️ 已自动撤销未完成的 tool_calls 记录")

        # 补齐断层信息，防上下文报错
        fake_msg = {"role": "assistant", "content": content_msg}
        if any("reasoning_content" in msg for msg in self.current_history if msg.get("role") == "assistant"):
            fake_msg["reasoning_content"] = ""
        self.current_history.append(fake_msg)

        self.save_checkpoint()


    def _check_and_summarize_memory(self, check_mode=True):
        max_tokens = 500000
        if check_mode and self.window_token < max_tokens:
            return

        print(f"🗜️ 记忆容量到达 {len(self.current_history)} 条 (约 {self.window_token} tokens)，触发自我归档...")

        try:
            # 1. 准备沙箱环境
            alert_prompt = """【系统警告：记忆容量即将溢出，触发自动记忆归档】
为了防止对话断层，系统即将清理你最早期的一批记忆。
你必须调用 `update_memo` 工具将当前记忆进行分类归档：
- short_term: 当前正在处理、被搁置的任务流，以及确立的全局变量或当前需要加载的工具、Skill等。
- long_term: 发现的明确用户喜好、做事风格或避坑经验。
- decisions: 技术发现与架构决策记录。
- reminders: 待办提醒事项。
- project_state: 当前项目整体进度。
注意：直接调用工具即可，无须输出废话。"""
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
        current_tools = list(BASE_TOOLS) + list(AGENT_TOOLS)
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
                    if t.function.name == "update_memo":
                        has_update_memo = True
                        try:
                            args_str = t.function.arguments
                            args = {}
                            if args_str:
                                try:
                                    args = json.loads(args_str)
                                except json.JSONDecodeError as e:
                                    print(f"⚠️ update_memo JSON 解析失败，尝试修复: {e}")
                                    if repair_json:
                                        args = repair_json(args_str, return_objects=True)

                            if isinstance(args, dict):
                                parse_tool("update_memo", args)
                                param_parts = []
                                for key, val in args.items():
                                    val_str = json.dumps(val, ensure_ascii=False) if isinstance(val, (dict, list)) else str(val)
                                    param_parts.append(f"  - **{key}**: {val_str}")

                                if param_parts:
                                    archived_contents.append("\n".join(param_parts))

                            tool_response = '✅ 归档工具调用成功'
                        except Exception as e:
                            print(f"⚠️ update_memo 执行异常: {e}")
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
                            tool_response = f'⚠️ update_memo 执行异常但已记录: {str(e)[:100]}'

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
                            "content": '❌ 系统拦截：当前处于强制归档阶段，请立刻调用 update_memo。'
                        })

                if has_update_memo:
                    archive_success = True
                    print("🧠 Agent归档完成，成功处理 update_memo 调用。")
                    break
                else:
                    temp_history.append({"role": "user", "content": "打回：你必须调用 `update_memo` 工具来归档备忘录！"})
            else:
                temp_history.append(assist_msg)
                temp_history.append(
                    {"role": "user", "content": "打回：你必须调用 `update_memo` 工具！请不要只回复纯文本。"})

        if archive_success:
            final_summary = "\n\n".join(archived_contents) if archived_contents else "（无归档细节）"
        else:
            print("⚠️ 未能成功调用 update_memo 工具，强制截断可能导致上下文丢失。")
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
    # ==========================================
    # 系统与运行控制
    # ==========================================
    def sensor(self):
        print("Agent 主核运转...")
        while not self._stop_event.is_set():
            try:
                has_pending = False
                with self._lock:
                    if self.pending_force_push:
                        has_pending = True
                if has_pending:
                    self.process_message()
                time.sleep(1)
            except Exception as e:
                print(f"❌ 主核运转异常: {e}")
                time.sleep(1)

    def save_checkpoint(self, filepath="src/agent/checkpoint.json"):
        save_path = filepath or self.checkpoint_path
        temp_path = f"{save_path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.current_history, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, save_path)
        except Exception as e:
            print(f"⚠️ [Checkpoint] 保存检查点失败: {e}")

    @classmethod
    def load_checkpoint(cls, filepath="src/agent/checkpoint.json", name=None):
        if not name:
            name = get_agent_model()
        agent = cls(name=name, checkpoint_path=filepath)
        try:
            if not os.path.exists(filepath):
                print(f"⚠️ [Checkpoint] 找不到文件: {filepath}，将以全新状态启动并创建该文件。")
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                agent.save_checkpoint(filepath)
                return agent
            with open(filepath, "r", encoding="utf-8") as f:
                history = json.load(f)
            if isinstance(history, list) and len(history) > 0:
                last_msg = history[-1]
                if last_msg.get("role") == "assistant" and last_msg.get("tool_calls"):
                    print("🛠️ [Checkpoint] 检测到断点处缺失工具回传结果，自动撤销最近一次未完成的思考...")
                    history.pop()
                agent.current_history = history
                if agent.current_history and agent.current_history[0].get("role") == "system":
                    agent.current_history[0]["content"] = agent.system_prompt
                print(f"✅ 成功从 {filepath} 恢复对话历史，共加载了 {len(history)} 条记录。")
            else:
                print(f"⚠️ [Checkpoint] 文件内容为空或格式错误，重置为全新状态。")
                agent.save_checkpoint(filepath)
            return agent
        except Exception as e:
            print(f"❌ [Checkpoint] 恢复检查点失败: {e}，将以全新状态启动。")
            return agent
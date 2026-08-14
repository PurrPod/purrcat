import asyncio
import os
import time
import uuid
import copy
import threading
import json
import datetime

from src.model import AgentModel
from src.tool.utils.route import dispatch_tool
from src.harness.utils.tool_helper import extract_tool_calling
from src.utils.path import convert_sandbox_path
from src.agent.session_store import SessionStore

# 全局后台活跃任务字典与专用的线程安全互斥锁
ACTIVE_SUB_TASKS = {}
SUB_TASK_LOCK = threading.Lock()


def cancel_sub_branch(branch_id: str) -> bool:
    """提供给外部 API 调用的强制斩杀后台分支任务的方法"""
    with SUB_TASK_LOCK:
        task_handle = ACTIVE_SUB_TASKS.get(branch_id)
        if task_handle:
            task_handle.cancel()
            return True
    return False


# ── 🌟 异步循环专用物理守护线程 ──
_SUB_LOOP = None
_SUB_THREAD = None
_LOOP_INIT_LOCK = threading.Lock()


def ensure_sub_loop():
    """驱动后台并发协程的底层常驻事件循环，优雅杜绝 no running event loop 报错"""
    global _SUB_LOOP, _SUB_THREAD
    if _SUB_LOOP is None:
        with _LOOP_INIT_LOCK:
            if _SUB_LOOP is None:
                _SUB_LOOP = asyncio.new_event_loop()
                _SUB_THREAD = threading.Thread(
                    target=lambda loop: (
                        asyncio.set_event_loop(loop),
                        loop.run_forever(),
                    ),
                    args=(_SUB_LOOP,),
                    name="BrainStorm_AsyncLoop_Thread",
                    daemon=True,
                )
                _SUB_THREAD.start()
    return _SUB_LOOP


class SubAgentRunner:
    def __init__(
        self,
        main_session_id: str,
        internal_branch_id: str,
        display_branch_id: str,
        action: str,
        deliverable: list,
        initial_history: list,
    ):
        self.main_session_id = main_session_id
        self.internal_branch_id = internal_branch_id  # 隔离的内部唯一 ID
        self.display_branch_id = display_branch_id  # 模型可见的极简 ID (b1)
        self.action = action
        self.window_token = 0  # 🌟 新增：用于追踪当前子分支的窗口 Token 消耗

        # 🌟 批量转换物理路径
        self.deliverable_paths = [convert_sandbox_path(d) for d in deliverable]

        # 隔离历史记录（从主分支历史点深拷贝）
        self.messages = copy.deepcopy(initial_history)
        self.model = AgentModel(task_id=f"{main_session_id}_sub_{internal_branch_id}")

    def _notify_main(self, content: str):
        from src.agent.manager import AgentManager

        AgentManager().agent_force_push(content, type="system")

    def _save_history(self):
        SessionStore.save_session(
            self.main_session_id,
            self.messages,
            branch_id=self.internal_branch_id,
            deliverable=self.deliverable_paths,
            action=self.action,
        )

    def _build_system_prompt(self):
        """🌟 为主模型动态重建系统提示词的方法，保持最新规则与技能/作坊状态同步"""
        soul_md, system_rules, memory_md = "", "", ""
        skills_info, workshops_info = "", ""

        def _extract_desc(file_path):
            if not os.path.exists(file_path):
                return None
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    in_front_matter = False
                    for line in f:
                        line = line.strip()
                        if line == "---":
                            if not in_front_matter:
                                in_front_matter = True
                                continue
                            else:
                                break

                        if in_front_matter and line.lower().startswith("description:"):
                            val = line.split(":", 1)[1].strip()
                            if (val.startswith('"') and val.endswith('"')) or (
                                val.startswith("'") and val.endswith("'")
                            ):
                                val = val[1:-1]
                            return val
            except Exception:
                pass
            return None

        try:
            from src.utils.config import (
                AGENT_CORE_DIR,
                SKILL_DIR,
                SOUL_MD_PATH,
                SYSTEM_RULES_DIR,
            )

            info_json_path = os.path.join(AGENT_CORE_DIR, "info.json")
            if os.path.exists(info_json_path):
                with open(info_json_path, "r", encoding="utf-8") as f:
                    info_data = json.load(f)

                skills = info_data.get("skills", [])
                if skills:
                    skills_info += "以下是核心skill，所有的skill以本清单为第一优先级，请在工作过程中遇到对应任务就使用Fetch工具进行调用！！！\n"
                    for skill in skills:
                        desc = _extract_desc(os.path.join(SKILL_DIR, skill, "SKILL.md"))
                        if desc:
                            skills_info += f"- {skill}:{desc}\n"
                        else:
                            skills_info += f"- {skill}（技能加载失败，可能未安装）\n"
                    skills_info += "对于本清单以外的其它普通skill，请使用Search工具进行检索和发现。\n"

                workshops = info_data.get("workshops", [])
                if workshops:
                    workshops_info += "以下是系统常驻作坊，请在收到特定任务的时候进入对应的文件夹内读取对应项目的AGENTS.md或WORKSHOP.md进行工作，\n"
                    for ws in workshops:
                        desc = _extract_desc(os.path.join(ws, "WORKSHOP.md"))
                        if desc:
                            workshops_info += f"- {ws}:{desc}\n"
                        else:
                            workshops_info += (
                                f"- {ws}（作坊加载失败，可能未找到WORKSHOP.md）\n"
                            )
                    workshops_info += "如无相关作坊，直接在沙盒内工作即可\n"

            MEMORY_MD_PATH = os.path.join(AGENT_CORE_DIR, "MEMORY.md")
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
            print(f"[Warn.SubAgent] Prompt 构建发生异常: {e}")

        combined = system_rules
        if soul_md:
            combined += f"\n\n---\n\n{soul_md}"

        if skills_info:
            combined += f"\n\n---\n\n# 【核心技能档案】\n\n{skills_info}"
        if workshops_info:
            combined += f"\n\n---\n\n# 【常驻作坊 (Workshops)】\n\n{workshops_info}"

        if memory_md:
            combined += f"\n\n---\n\n# 【系统长期记忆档案】\n\n{memory_md}"

        return combined

    async def _truncate_memory_if_needed(self):
        """🌟 新增：SubAgent专属同款记忆总结压缩机制（异步阻塞式拦截与严格校验）"""
        from src.utils.config import get_model_config
        from src.tool import AGENT_TOOL_SCHEMA

        model_cfg = (
            get_model_config().get("main", {}).get(self.model.model_name or "", {})
        )
        max_tokens = model_cfg.get("max_token", 500000)
        if self.window_token < max_tokens:
            return

        print(
            f"[Truncate.SubAgent] 触发后台会话记忆截断 (当前约 {self.window_token} tokens)，请求大总结..."
        )
        now_str = datetime.datetime.now().strftime("%m-%d %H:%M:%S")

        # 1. 构造用于触发总结的临时指令 (type=system 注入)
        compression_prompt = {
            "role": "user",
            "content": json.dumps(
                {
                    "events": [
                        {
                            "type": "system",
                            "time": now_str,
                            "content": "记忆窗口已达上限，系统将要删除所有对话历史。为防止上下文断层，请对当前所有会话细节、历史、当前工作记忆与进度进行大总结，然后调用 Memo 工具（必须设置 action='add'）传入总结报告。系统将仅保留这份总结。",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        }

        temp_history = self.messages.copy() + [compression_prompt]

        # 2. 阻塞式网络交互：请求模型，重试 3 次及过滤拦截
        summary_text = None
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            try:
                response = await asyncio.to_thread(
                    self.model.chat, messages=temp_history, tools=AGENT_TOOL_SCHEMA
                )
                msg_resp = response.choices[0].message
                valid_memo_found = False

                # 拦截提取工具参数，拒绝向下派发和实际执行
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
                            except Exception:
                                pass

                if valid_memo_found:
                    break
                else:
                    # 校验失败：丢弃模型回复，直接追加 type=system 的 User 警告
                    warning_msg = f"【第{attempt}次警告】未使用Memo工具进行记忆总结(或 action 不为 'add')！请只调用 Memo 工具并将 action 设为 'add'，不要完成无关工作。"
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
                    print(f"[Warn.SubAgentBlock] {warning_msg}")

            except Exception as e:
                print(f"[Error] 后台记忆总结请求网络异常: {e}")
                break

        # 兜底降级处理
        if not summary_text:
            if "msg_resp" in locals() and msg_resp.content:
                summary_text = msg_resp.content
            else:
                summary_text = "（后台子分支未能成功生成有效总结，上下文已强行截断）"

        # 3. 开始重建子分支真实历史
        try:
            original_len = len(self.messages)
            keep_recent = 10
            split_idx = original_len - keep_recent

            # 寻找安全截断点
            if split_idx > 1:
                while split_idx > 1:
                    curr_msg = self.messages[split_idx]
                    prev_msg = self.messages[split_idx - 1]
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

            recent_messages = self.messages[split_idx:original_len]

            # 重建最新的系统提示词
            fresh_system_content = self._build_system_prompt()
            new_system_msg = {"role": "system", "content": fresh_system_content}

            # 包装记忆总结为 type=system 事件
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

            # 组装最终历史：【重建系统提示词】+ 【最近10条信息】+ 【记忆大总结】
            self.messages = [new_system_msg] + recent_messages + [summary_msg]

            # 剔除思维链过程
            for msg in self.messages:
                if msg.get("role") == "assistant" and "reasoning_content" in msg:
                    msg["reasoning_content"] = ""

            print("[Success] 后台子分支记忆大总结与安全截断完毕！")
            self.window_token = 0
            self._save_history()

        except Exception as e:
            print(f"[Error] 后台历史重组发生严重异常: {e}")

    async def run(self):
        # 🌟 修复 1：把数组拼接成可读的列表展示给大模型
        deliverable_txt = "\n".join([f"- {p}" for p in self.deliverable_paths])
        user_inject = (
            f"当前你已被分配到分支 {self.display_branch_id}。\n\n"
            f"你需要：{self.action}\n\n"
            f"交付物要求（请生成以下文件）：\n{deliverable_txt}\n\n"
            f"请全力完成交付物生成，完成后请立即停止调用任何工具，请勿染指无关事项。"
        )
        self.messages.append({"role": "user", "content": user_inject})
        self._save_history()  # 立刻落盘

        turn_count = 0
        start_time = time.time()
        warning_sent = False
        tool_call_after_generated_turns = 0

        while True:
            # 🌟 0. 驱动模型前，首先进行记忆压缩检测（搬运同款核心拦截逻辑）
            await self._truncate_memory_if_needed()

            # 1. 软限制轮询告警
            elapsed_time = time.time() - start_time
            if not warning_sent and (turn_count >= 15 or elapsed_time > 600):
                self._notify_main(
                    f"[Warn.Monitor] 后台分支 `{self.display_branch_id}` 已自主运行了 {turn_count} 轮 / {int(elapsed_time)} 秒。\n"
                    f"如确信其陷入困境，主干可执行 BrainStorm(action='cancel', target_branch_id='{self.display_branch_id}') 将其强杀。"
                )
                warning_sent = True

            # 2. 驱动大模型聊天
            from src.tool import AGENT_TOOL_SCHEMA

            response = await asyncio.to_thread(
                self.model.chat, messages=self.messages, tools=AGENT_TOOL_SCHEMA
            )

            # 🌟 追踪 Token 进度
            if response and hasattr(response, "usage") and response.usage:
                self.window_token = response.usage.total_tokens

            msg_resp = response.choices[0].message
            assist_msg = {"role": "assistant", "content": msg_resp.content or ""}

            # 🌟 完整提取并保留深度思考过程
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
            self.messages.append(assist_msg)
            self._save_history()  # 大模型回复后立即落盘

            tool_calls = extract_tool_calling(response)

            # 🌟 检查所有的文件或目录是否都存在（如果是文件则额外检查不为空）
            missing_files = []
            for p in self.deliverable_paths:
                if not os.path.exists(p):
                    missing_files.append(p)
                elif os.path.isfile(p) and os.path.getsize(p) == 0:
                    missing_files.append(p)

            file_ready = len(missing_files) == 0  # 如果没有缺失文件，就是 ready
            turn_count += 1

            # 3. 契约验收逻辑 (无工具调用时)
            if not tool_calls:
                if file_ready:
                    self._notify_main(
                        f"[Success.Report] 子分支 `{self.display_branch_id}` 任务已圆满结束！所有目标交付物文件均已就绪且内容不为空。"
                    )
                    break
                else:
                    missing_txt = "\n".join([f"- {p}" for p in missing_files])
                    self.messages.append(
                        {
                            "role": "user",
                            "content": f"任务未结束：未在沙盒中检测到以下要求的交付物文件，或者文件目前为空。请确保生成并写入具体内容：\n{missing_txt}",
                        }
                    )
                    self._save_history()  # 验收失败追加 prompt 后落盘
                    continue

            # 4. 安全调用底层工具箱
            for tc in tool_calls:
                import json

                tool_name = tc.function.name
                args = (
                    json.loads(tc.function.arguments) if tc.function.arguments else {}
                )

                # 🚫 核心注入保护：告知整个路由分发器当前是 Sub 分支
                args["_is_sub_branch"] = True
                if tool_name == "Bash":
                    args["session_id"] = (
                        f"{self.main_session_id}_{self.internal_branch_id}"
                    )

                result = await asyncio.to_thread(dispatch_tool, tool_name, args)
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tool_name,
                        "content": result,
                    }
                )
                self._save_history()  # 工具执行后落盘

            # 5. 防加戏死循环拦截
            if file_ready:
                tool_call_after_generated_turns += 1
                if tool_call_after_generated_turns > 3:
                    self.messages.append(
                        {
                            "role": "user",
                            "content": f"本分支任务为：{self.action}。检测到你已成功生成交付物且内容完整，不允许去完成本分支以外的工作防产生冲突，请迅速停止调用工具并收尾。",
                        }
                    )
                    self._save_history()  # 记得补充落盘
            else:
                tool_call_after_generated_turns = 0


async def run_dag_graph(sub_branches: list, main_session_id: str, main_history: list):
    """带命名空间多文件隔离、带拓扑依赖等待的后台并发核心调度引擎"""
    plan_batch_id = uuid.uuid4().hex[
        :6
    ]  # 🌟 每次调用分配唯一批次号，防止 b1, b2 命名冲突

    internal_id_map = {
        b["branch_id"]: f"{plan_batch_id}_{b['branch_id']}" for b in sub_branches
    }
    events = {internal_id_map[b["branch_id"]]: asyncio.Event() for b in sub_branches}

    async def run_single_branch(b_info):
        display_id = b_info["branch_id"]
        internal_id = internal_id_map[display_id]

        # 串行/并行网关依赖等待
        for dep in b_info.get("depends_on", []):
            if dep in internal_id_map:
                await events[internal_id_map[dep]].wait()

        runner = SubAgentRunner(
            main_session_id=main_session_id,
            internal_branch_id=internal_id,
            display_branch_id=display_id,
            action=b_info["action"],
            deliverable=b_info["deliverable"],
            initial_history=main_history,
        )

        loop_task = asyncio.create_task(runner.run())

        with SUB_TASK_LOCK:
            ACTIVE_SUB_TASKS[display_id] = loop_task

        try:
            await loop_task
        except asyncio.CancelledError:
            runner._notify_main(f"🛑 后台分支 `{display_id}` 已被取消。")
        finally:
            with SUB_TASK_LOCK:
                ACTIVE_SUB_TASKS.pop(display_id, None)
            events[internal_id].set()

    await asyncio.gather(*(run_single_branch(b) for b in sub_branches))

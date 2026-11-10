import asyncio
import os
import time
import uuid
import copy
import threading
import json

from src.agent.compression import (
    COMPRESSION_INSTRUCTION,
    SUB_SUMMARY_FALLBACK,
    rebuild_sub_history,
    run_summary_attempts,
    sub_warning,
)
from src.agent.system_prompt import build_sub_system_prompt
from src.model import AgentModel
from src.tool.utils.route import (
    dispatch_tool,
    extract_tool_message_content,
)
from src.harness.utils.tool_helper import extract_tool_calling
from src.utils.path import convert_sandbox_path
from src.agent.session_store import SessionStore

# 全局后台活跃任务字典与专用的线程安全互斥锁
ACTIVE_SUB_TASKS = {}
SUB_TASK_LOCK = threading.Lock()


def cancel_sub_branch(branch_id: str, wait: bool = False) -> bool:
    """提供给外部 API 调用的强制斩杀后台分支任务的方法。

    兼容两种 id：
      - display id（如 ``b1``）：ACTIVE_SUB_TASKS 的键，BrainStorm cancel 工具用；
      - 内部 id（如 ``ab12cd_b1``）：meta.json 里存储的分支键，删除分支 API 用。
    内部 id 形如 ``{batch}_{display}``，故按 ``_`` 后缀反查即可命中同一任务，
    保证「删除分支」能真正杀掉后台子代理，而不是只删掉元数据。

    ``wait=True`` 时阻塞直到后台协程真正收敛（run_single_branch 的 finally 里会把
    key 弹出）。删除分支必须先 wait 再删文件/元数据：否则 cancel 后协程仍可能在其
    当前同步片段里执行一次 _save_history()，把刚删掉的分支「复活」。
    """
    if not branch_id:
        return False
    matched_keys = []
    with SUB_TASK_LOCK:
        handles = []
        if branch_id in ACTIVE_SUB_TASKS:
            # 内部 id（{batch}_{display}）全局唯一，精确命中
            handles.append(ACTIVE_SUB_TASKS[branch_id])
            matched_keys.append(branch_id)
        else:
            # 传入 display id（如 b1）时：跨批次匹配所有 {batch}_b1
            # （多个批次可能同时存在同名的 b1，此时全部取消）
            for key, handle in ACTIVE_SUB_TASKS.items():
                if key == branch_id or key.endswith("_" + branch_id):
                    handles.append(handle)
                    matched_keys.append(key)
        if not handles:
            return False
        for h in handles:
            h.cancel()

    # 锁外轮询等待全部收敛，避免与 finally 抢锁造成死锁
    if wait:
        deadline = time.time() + 5.0
        while time.time() < deadline:
            with SUB_TASK_LOCK:
                if not any(k in ACTIVE_SUB_TASKS for k in matched_keys):
                    break
            time.sleep(0.02)
    return True


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
        self.consumed_tokens = (
            0  # 🌟 本子分支累计消耗（所有 LLM 调用 usage.total_tokens 之和）
        )

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
            consumed_tokens=self.consumed_tokens,
        )

    def _build_system_prompt(self):
        """🌟 为主模型动态重建系统提示词的方法，保持最新规则与技能/作坊状态同步"""
        return build_sub_system_prompt()

    async def _truncate_memory_if_needed(self):
        """🌟 SubAgent 专属记忆总结压缩机制（异步阻塞式拦截与严格校验）"""
        from src.utils.config import get_model_max_token
        from src.tool import AGENT_TOOL_SCHEMA

        max_tokens = get_model_max_token(self.model.model_name or None)
        if self.window_token < max_tokens:
            return

        print(
            f"[Truncate.SubAgent] 触发后台会话记忆截断 (当前约 {self.window_token} tokens)，请求大总结..."
        )

        temp_history = self.messages.copy()
        summary_text = await asyncio.to_thread(
            run_summary_attempts,
            lambda messages: self.model.chat(
                messages=messages, tools=AGENT_TOOL_SCHEMA
            ),
            temp_history,
            instruction=COMPRESSION_INSTRUCTION,
            warning_text=sub_warning,
            fallback_text=SUB_SUMMARY_FALLBACK,
            warning_prefix="[Warn.SubAgentBlock]",
            error_prefix="[Error] 后台记忆总结请求网络异常",
        )

        try:
            self.messages = rebuild_sub_history(
                self.messages,
                self._build_system_prompt(),
                summary_text,
            )
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
                total_tokens = getattr(response.usage, "total_tokens", 0) or 0
                self.window_token = total_tokens
                self.consumed_tokens += total_tokens

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
                    notify_text = f"[Success.Report] 子分支 `{self.display_branch_id}` 任务已圆满结束！所有目标交付物文件均已就绪且内容不为空。"
                    # 🌟 附加子代理最后一条回复，让主干无需读文件即可拿到收尾汇报
                    final_reply = (msg_resp.content or "").strip()
                    if final_reply:
                        MAX_REPLY_LEN = 1000
                        snippet = final_reply[:MAX_REPLY_LEN]
                        omitted = len(final_reply) - MAX_REPLY_LEN
                        if omitted > 0:
                            snippet += f"\n...(后续 {omitted} 字符已截断，完整内容见该分支的会话记录)"
                        notify_text += f"\n--- 子代理收尾汇报 ---\n{snippet}"
                    self._notify_main(notify_text)
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

                result = await asyncio.to_thread(
                    dispatch_tool,
                    tool_name,
                    args,
                    vision_mode=getattr(self.model, "vision", False),
                )
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tool_name,
                        # vision 直注时为 OpenAI 多模态 parts 列表
                        "content": extract_tool_message_content(result),
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
            # 🌟 以内部 id（{batch}_{display}，全局唯一）为键注册，避免并发批次
            # 的同名 b1/b2 互相覆盖，导致取消/删除误伤或提前 pop。
            ACTIVE_SUB_TASKS[internal_id] = loop_task

        try:
            await loop_task
        except asyncio.CancelledError:
            runner._notify_main(f"🛑 后台分支 `{display_id}` 已被取消。")
        finally:
            with SUB_TASK_LOCK:
                ACTIVE_SUB_TASKS.pop(internal_id, None)
            events[internal_id].set()

    await asyncio.gather(*(run_single_branch(b) for b in sub_branches))

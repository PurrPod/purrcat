import asyncio
import os
import time
import uuid
import copy
import threading

from src.model import AgentModel
from src.tool.utils.route import dispatch_tool
from src.harness.utils.tool_helper import extract_tool_calling
from src.utils.config import AGENT_VM_DIR
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
        deliverable: str,
        initial_history: list,
    ):
        self.main_session_id = main_session_id
        self.internal_branch_id = internal_branch_id  # 隔离的内部唯一 ID
        self.display_branch_id = display_branch_id  # 模型可见的极简 ID (b1)
        self.action = action
        self.deliverable_path = (
            deliverable.replace("/agent_vm", AGENT_VM_DIR, 1)
            if deliverable.startswith("/agent_vm")
            else deliverable
        )

        # 隔离历史记录（从主分支历史点深拷贝）
        self.messages = copy.deepcopy(initial_history)
        self.model = AgentModel(task_id=f"{main_session_id}_sub_{internal_branch_id}")

    def _notify_main(self, content: str):
        from src.agent.manager import AgentManager

        AgentManager().agent_force_push(content, type="system")

    # 🌟 新增：统一的存盘方法
    def _save_history(self):
        SessionStore.save_session(
            self.main_session_id,
            self.messages,
            branch_id=self.internal_branch_id,
            deliverable=self.deliverable_path,
            action=self.action,
        )

    async def run(self):
        # 🌟 修复 1：改为 user 角色，并按要求定制话术
        user_inject = (
            f"当前你已被分配到分支 {self.display_branch_id}。\n"
            f"你需要：{self.action}\n"
            f"交付物要求（请生成以下文件）：{self.deliverable_path}\n"
            f"请全力完成交付物生成，完成后请立即停止调用任何工具，请勿染指无关事项。"
        )
        self.messages.append({"role": "user", "content": user_inject})
        self._save_history()  # 立刻落盘

        turn_count = 0
        start_time = time.time()
        warning_sent = False
        tool_call_after_generated_turns = 0

        while True:
            # 1. 软限制轮询告警
            elapsed_time = time.time() - start_time
            if not warning_sent and (turn_count >= 15 or elapsed_time > 600):
                self._notify_main(
                    f"⚠️ [后台监控] 后台分支 `{self.display_branch_id}` 已自主运行了 {turn_count} 轮 / {int(elapsed_time)} 秒。\n"
                    f"如确信其陷入困境，主干可执行 BrainStorm(action='cancel', target_branch_id='{self.display_branch_id}') 将其强杀。"
                )
                warning_sent = True

            # 2. 驱动大模型聊天
            from src.tool import AGENT_TOOL_SCHEMA

            response = await asyncio.to_thread(
                self.model.chat, messages=self.messages, tools=AGENT_TOOL_SCHEMA
            )
            msg_resp = response.choices[0].message

            assist_msg = {"role": "assistant", "content": msg_resp.content or ""}

            # 🌟 修复：完整提取并保留深度思考过程，确保发给服务端的历史能完美匹配缓存单元
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
            self._save_history()  # 🌟 修复 2：大模型回复后立即落盘

            tool_calls = extract_tool_calling(response)

            # 🌟 修改 1：同时检测文件存在且大小大于 0（非空）
            file_ready = (
                os.path.exists(self.deliverable_path)
                and os.path.getsize(self.deliverable_path) > 0
            )
            turn_count += 1

            # 3. 契约验收逻辑 (无工具调用时)
            if not tool_calls:
                if file_ready:
                    self._notify_main(
                        f"✅ [后台捷报] 子分支 `{self.display_branch_id}` 任务已圆满结束！目标交付物文件已就绪且内容不为空。"
                    )
                    break
                else:
                    self.messages.append(
                        {
                            "role": "user",
                            "content": f"任务未结束：未在沙盒中检测到要求的交付物文件 {self.deliverable_path}，或者该文件目前为空，请确保生成并写入具体内容。",
                        }
                    )
                    self._save_history()  # 验收失败追加 prompt 后落盘
                    continue

            # 4. 安全调用底层工具箱 (🌟 修改 2：必须把执行工具放在注入 User 提示之前，保证 Tool Chain 完整闭环)
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

            # 5. 防加戏死循环拦截 (🌟 修改 3：在工具结果成功落盘闭环后，再判断是否需要强行塞入 User 警告)
            if file_ready:
                tool_call_after_generated_turns += 1
                if tool_call_after_generated_turns > 5:
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

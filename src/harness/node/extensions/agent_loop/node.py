import asyncio
import json
import os
from typing import Any, Dict

import yaml

from src.agent.hook_handler import HookHandler
from src.harness.node.agent_node import AgentNode
from src.harness.utils.llm_helper import call_llm
from src.harness.utils.tool_helper import extract_tool_calling, get_system_schema
from src.utils.config import AGENT_VM_DIR
from src.utils.paradigm_api import resolve_paradigm_path

SANDBOX_TASKSPACE_ROOT = "/agent_vm/_taskspace"


def taskspace_paths(task_name: str, task_id: str, node_id: str) -> tuple[str, str]:
    """返回 (宿主机目录, 沙盒视角目录)。

    目录名由任务名与 task_id 共同构成：任务名仅用于可读，task_id 保证同名任务
    互不覆盖；同一任务（含续跑）的 task_id 不变，目录仍然稳定复用。
    """
    segment = f"{task_name}_{task_id}"
    host_dir = os.path.join(AGENT_VM_DIR, "_taskspace", segment, node_id)
    sandbox_dir = f"{SANDBOX_TASKSPACE_ROOT}/{segment}/{node_id}"
    return host_dir, sandbox_dir


class Node(AgentNode):
    """范式（agentloop）驱动的智能体循环，与 src/agent 主循环语义对齐。

    - 输入一个符合 YAML 格式的 agentloop（也可传范式名或绝对路径），按 hook 驱动执行；
    - 循环终止：模型不再调用工具且 on_loop_end 全部通过（尊重 expect: fail 与 loop_end_max_retry）；
    - summary：优先读取 @TASKSPACE/<summary_file>，缺失回退最后一条 assistant 文本。
    """

    def _resolve_agentloop(self, raw, context) -> tuple:
        """解析 agentloop 输入，返回 (config_dict, paradigm_path_or_None)。"""
        if isinstance(raw, dict):
            return raw, None

        if isinstance(raw, str) and raw.strip():
            text = raw.strip()
            try:
                loaded = yaml.safe_load(text)
            except Exception:
                loaded = None
            if isinstance(loaded, dict) and ("hooks" in loaded or "name" in loaded):
                return loaded, None
            # 否则视为范式名或绝对路径
            if os.path.isabs(text) and os.path.exists(text):
                with open(text, "r", encoding="utf-8") as f:
                    return (yaml.safe_load(f) or {}), text
            path = resolve_paradigm_path(text)
            self.log(context, "SYSTEM", f"📄 [AgentLoop] 从范式文件加载: {path}")
            with open(path, "r", encoding="utf-8") as f:
                return (yaml.safe_load(f) or {}), path

        # 未提供 agentloop：按「空范式」执行，不加载任何钩子（不回退默认范式）
        self.log(
            context,
            "SYSTEM",
            "📄 [AgentLoop] 未提供 agentloop，按空范式执行（不响应任何钩子）",
        )
        return {}, None

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "🤖 [Agent循环] 开始执行（范式驱动）")

        # 1) 构建 hook 执行器
        config_dict, paradigm_path = self._resolve_agentloop(
            self.unpack(inputs, "agentloop"), context
        )
        handler = HookHandler(config_dict=config_dict, paradigm_path=paradigm_path)

        # 2) taskspace（按 (task_name, task_id, node_id) 稳定复用：同一任务续跑复用，
        #    同名任务互不覆盖）
        taskspace_host, sandbox_dir = taskspace_paths(
            context.task_name, context.task_id, self.node_id
        )
        os.makedirs(taskspace_host, exist_ok=True)
        handler.add_alias("@TASKSPACE", host_path=taskspace_host, content=sandbox_dir)
        self.log(context, "SYSTEM", f"🗂️ [TASKSPACE] 专属工作目录: {sandbox_dir}")

        # 3) 记忆 + 上游 messages + 系统提示 + force_push
        #    （只组装、不落盘；统一到本步末尾按「最终顺序」一次性写入）
        memory = self.load_memory_from_file(context)
        newly_user = []

        # 注入触发的「续跑」：记忆里已经吸收了上游上下文，不能再吸收一次
        # （否则上游整段重复入记忆，前端会看到同一条 user 消息出现两遍）
        skip_upstream = context.node_memory.setdefault(self.node_id, {}).pop(
            "skip_upstream", False
        )

        upstream = self.unpack(inputs, "messages") or []
        if skip_upstream:
            upstream = []

        # graph 专属：范式「构建系统提示」的输出与主 Agent 不同——主 Agent 里它是
        # system 头部；这里只把内容包成一条 role=user、type=system_input 的消息卡片，
        # 默认追加到「上游输入」的末尾——只追加、不动前缀，KV Cache 天然安全。
        # 只在「从零开始的会话」（本节点记忆尚为空）注入一次，重跑 / 续跑不重复追加。
        sys_msgs = []
        if not memory:
            results = handler.execute("on_build_system_prompt", epoch=0)
            parts = [r["inject_prompt"] for r in results if r.get("inject_prompt")]
            if parts:
                card = {"type": "system_input", "content": "\n\n---\n\n".join(parts)}
                sys_msgs = [
                    {"role": "user", "content": json.dumps(card, ensure_ascii=False)}
                ]

        if upstream:
            newly_user += [m for m in upstream if m.get("role") == "user"]

        pending = context.node_memory.setdefault(self.node_id, {}).pop("force_push", [])
        fps = []
        if pending:
            self.log(context, "SYSTEM", f"🔔 [人工指令] 收到 {len(pending)} 条人工指令")
            fps = [
                {
                    "role": "user",
                    "content": json.dumps(
                        {"type": "workflow_input", "content": f"[人工指令] {m}"},
                        ensure_ascii=False,
                    ),
                }
                for m in pending
            ]
            newly_user += fps

        # 最终顺序：记忆 → 上游输入 → 系统提示(user) → 人工指令
        messages = self._sanitize_messages(memory + upstream + sys_msgs + fps)

        # 4) on_input_received：只对本批新增的 type=user 输入触发
        # （系统提示 system_input 不计入本批输入，也不触发该钩子）
        if newly_user:
            await self._fire_hooks(
                handler,
                "on_input_received",
                messages,
                context,
                epoch=0,
                received_messages=[
                    {"type": "user", "content": str(m.get("content", ""))}
                    for m in newly_user
                ],
            )

        # 🌟 本批新增内容按内存里的「最终顺序」一次性落盘：
        # 各写各的 append 会让文件顺序与喂给模型的顺序错位（前缀对不上 → KV Cache 失效）。
        fresh = upstream + sys_msgs + fps
        if fresh:
            await asyncio.to_thread(self.append_memory_to_file, context, fresh)

        # 5) on_loop_start
        await self._fire_hooks(handler, "on_loop_start", messages, context, epoch=0)

        # 6) 主循环
        tools = get_system_schema()
        used_tools: Dict[str, list] = {}
        loop_epoch = 0
        loop_end_retry = 0
        last_assistant_text = ""

        while True:
            loop_epoch += 1
            self.log(
                context, "SYSTEM", f"🔄 [Agent循环] 开始新一轮思考 (epoch={loop_epoch})"
            )
            await self._fire_hooks(
                handler, "on_loop_epoch", messages, context, epoch=loop_epoch
            )

            response, messages = await call_llm(context.model, messages, tools)
            self._accumulate_tokens(context, response)
            assistant_msg = response.choices[0].message

            finish_reason = getattr(response.choices[0], "finish_reason", None)
            if finish_reason == "length":
                self.log(
                    context,
                    "WARNING",
                    "⚠️ [输出截断] 模型输出因长度上限被截断，本轮工具参数可能不完整",
                )

            if assistant_msg.content:
                last_assistant_text = assistant_msg.content
                preview = (
                    assistant_msg.content[:200] + "..."
                    if len(assistant_msg.content) > 200
                    else assistant_msg.content
                )
                self.log(context, "SYSTEM", f"💭 [模型回复] {preview}")

            await asyncio.to_thread(self.append_memory_to_file, context, [messages[-1]])
            await asyncio.to_thread(self._sync_dump_memory, context, messages)

            tool_calls = extract_tool_calling(response)
            if tool_calls:
                self.log(
                    context,
                    "SYSTEM",
                    f"🔧 [工具调用] 检测到 {len(tool_calls)} 个工具调用",
                )
                current_tools: Dict[str, list] = {}
                for t in tool_calls:
                    args = {}
                    if t.function.arguments:
                        try:
                            args = json.loads(t.function.arguments)
                        except Exception:
                            args = {}
                    used_tools.setdefault(t.function.name, []).append(args)
                    current_tools.setdefault(t.function.name, []).append(args)

                tool_msgs = await self.run_tool_calls(response, context)
                messages.extend(tool_msgs)
                if tool_msgs:
                    await asyncio.to_thread(
                        self.append_memory_to_file, context, tool_msgs
                    )
                    await asyncio.to_thread(self._sync_dump_memory, context, messages)

                await self._fire_hooks(
                    handler,
                    "on_tool_calling",
                    messages,
                    context,
                    epoch=loop_epoch,
                    used_tools=current_tools,
                )
                continue

            # 无工具调用 → 判定是否结束循环
            all_success = await self._fire_hooks(
                handler,
                "on_loop_end",
                messages,
                context,
                epoch=loop_epoch,
                used_tools=used_tools,
                loop_end_retry=loop_end_retry,
            )
            if all_success:
                self.log(
                    context, "SYSTEM", "✅ [循环结束] 所有结束条件通过，正常关闭循环"
                )
                break

            loop_end_retry += 1
            hint = {
                "type": "workflow_hint",
                "content": "未满足结束循环条件，已自动打回",
            }
            hint_msg = {"role": "user", "content": json.dumps(hint, ensure_ascii=False)}
            messages.append(hint_msg)
            await asyncio.to_thread(self.append_memory_to_file, context, [hint_msg])
            # 🌟 打回提示是 workflow_hint 系统注入，不算收到用户输入，不触发钩子

        # 7) summary：优先 @TASKSPACE/<summary_file>，回退最后 assistant 文本
        summary = self._read_summary(context, taskspace_host)
        if not summary:
            summary = last_assistant_text or "任务完成"

        display_summary = (
            str(summary)[:1500] + "..." if len(str(summary)) > 1500 else str(summary)
        )
        self.log(context, "SYSTEM", f"📊 [总结内容]:\n{display_summary}")
        return {"messages": messages, "summary": summary}

    async def _fire_hooks(self, handler, stage, messages, context, **kwargs):
        """执行 hook → 以 role=user 注入 inject_prompt。

        注入的都是 workflow_hint（系统提示），不算「收到用户输入」，因此不会触发
        on_input_received（只有本批新增的 type=user 输入才触发）。
        返回 all_success（无 hook 时视为 True）。
        """
        results = handler.execute(stage, **kwargs)
        all_success = all(r.get("success") for r in results) if results else True

        injected = []
        for r in results:
            if r.get("inject_prompt"):
                hint = {"type": "workflow_hint", "content": r["inject_prompt"]}
                msg = {"role": "user", "content": json.dumps(hint, ensure_ascii=False)}
                messages.append(msg)
                injected.append(hint)

        if injected:
            await asyncio.to_thread(
                self.append_memory_to_file, context, messages[-len(injected) :]
            )

        return all_success

    @staticmethod
    def _accumulate_tokens(context, response):
        usage = getattr(response, "usage", None)
        if usage and hasattr(context, "total_tokens"):
            with context._lock:
                context.total_tokens += usage.total_tokens

    def _read_summary(self, context, taskspace_host) -> str:
        filename = (self.config.get("summary_file") or "summary.txt").strip()
        path = os.path.join(taskspace_host, filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                if text:
                    self.log(context, "SYSTEM", f"📥 [总结转递] 读取 {filename} 成功")
                    return text
            except Exception as e:
                self.log(context, "WARNING", f"⚠️ [总结读取失败] {e}")
        return ""

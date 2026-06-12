import asyncio
import json
import os
from typing import Any, Dict

from src.harness.enums import NodeState
from src.harness.node.agent_node import AgentNode
from src.utils.config import AGENT_VM_DIR


class Node(AgentNode):
    """全能 Agent 循环：支持纯文本总结，也支持多文件强制验收"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "🤖 [Agent循环] 开始执行")

        dynamic_info = inputs.get("task_done_info")
        if dynamic_info:
            try:
                if isinstance(dynamic_info, str):
                    self.task_done_info = json.loads(dynamic_info)
                elif isinstance(dynamic_info, dict):
                    self.task_done_info = dynamic_info
                self.log(
                    context,
                    "SYSTEM",
                    f"🎯 [强制验收目标]:\n{json.dumps(self.task_done_info, indent=2, ensure_ascii=False)}",
                )
            except Exception as e:
                self.log(
                    context,
                    "WARNING",
                    f"⚠️ [动态规则挂载] 解析失败，将不使用强校验: {e}",
                )
        else:
            self.log(
                context,
                "SYSTEM",
                "ℹ️ [动态规则] 未收到动态规则，使用默认配置",
            )

        my_memory = context.node_memory.setdefault(self.node_id, {})

        # ========================================================
        # 🌟 核心修复开始：适配新架构，从节点专属的独立硬盘文件加载记忆
        mem_path = self.get_memory_file_path(context)
        messages = []
        if os.path.exists(mem_path):
            with open(mem_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(json.loads(line))

        # 🌟 如果硬盘里没记忆（说明是首次运行），才把上游数据塞入并落盘，防止重复塞入
        if not messages:
            upstream_msgs = inputs.get("messages", [])
            if upstream_msgs:
                messages.extend(upstream_msgs)
                await asyncio.to_thread(
                    self.append_memory_to_file, context, upstream_msgs
                )

        # 🌟 提取人工干预的指令，并立刻追加落盘防丢失
        pending_push = my_memory.pop("force_push", [])
        if pending_push:
            self.log(
                context, "SYSTEM", f"🔔 [人工指令] 收到 {len(pending_push)} 条人工指令"
            )
            force_push_msgs = [
                {"role": "user", "content": f"[人工指令] {msg}"} for msg in pending_push
            ]
            messages.extend(force_push_msgs)
            await asyncio.to_thread(
                self.append_memory_to_file, context, force_push_msgs
            )
        # 核心修复结束
        # ========================================================

        target_files_raw = inputs.get("target_files") or self.config.get(
            "target_files", []
        )
        if isinstance(target_files_raw, str):
            target_files = [f.strip() for f in target_files_raw.split(",") if f.strip()]
        else:
            target_files = target_files_raw

        check_paths = []
        if target_files:
            self.log(context, "SYSTEM", f"📁 [文件验收] 目标文件列表: {target_files}")
            for fpath in target_files:
                if not fpath.startswith("/agent_vm"):
                    raise ValueError(f"文件路径必须以 '/agent_vm' 开头: {fpath}")
                check_paths.append(fpath.replace("/agent_vm", AGENT_VM_DIR, 1))
        else:
            self.log(context, "SYSTEM", "📁 [文件验收] 无目标文件，将直接输出总结")

        # ========================================================
        # 🌟 新增：注入 task_done 工具使用说明与格式强校验文案 (User角色)
        # ========================================================
        task_done_prompt = (
            "【任务完结要求】\n"
            "当你认为已经完成了本阶段的核心思考和所有必要操作后，请务必调用 `task_done` 工具来标注任务已完成并移交控制权。\n"
        )

        if getattr(self, "task_done_info", None):
            task_done_prompt += "⚠️ 注意：调用 `task_done` 工具时，你的 `summary` 参数必须严格包含以下 JSON 字段及内容：\n"
            for key, desc in self.task_done_info.items():
                task_done_prompt += f'  - "{key}": {desc}\n'
        else:
            task_done_prompt += "⚠️ 注意：调用 `task_done` 工具时，请在 `summary` 参数中输出详尽的任务执行总结。\n"

        # 检查是否已经注入过该提示（防止任务挂起恢复或重跑时重复写入）
        has_injected = False
        for msg in messages[-5:]:
            if msg.get("role") == "user" and "【任务完结要求】" in msg.get(
                "content", ""
            ):
                has_injected = True
                break

        if not has_injected:
            # 修改点：这里将 role 从 system 改为了 user
            user_msg = {"role": "user", "content": task_done_prompt}
            messages.append(user_msg)
            # 立刻追加落盘，保证前端气泡也能看到这条明确的指令
            await asyncio.to_thread(self.append_memory_to_file, context, [user_msg])
        # ========================================================

        tools = self.get_all_tools()

        MAX_ERRORS = 3
        error_count = 0

        # 🌟 修复：获取当前节点的专属记忆文件路径
        mem_path = self.get_memory_file_path(context)

        try:
            while True:
                self.log(context, "SYSTEM", "🔄 [Agent循环] 开始新一轮思考...")

                # 🌟 修复：将 mem_path 传给底层，彻底激活 LLM 回复后的实时追加落盘特性！
                loop_result = await self.run_agent_loop(
                    context, messages, tools, mem_path
                )
                messages = loop_result["messages"]
                summary = loop_result["summary"]

                if not check_paths:
                    self.log(
                        context, "SYSTEM", "✅ [任务完结] 无文件校验需求，输出总结。"
                    )
                    display_summary = (
                        str(summary)[:1500] + "..."
                        if len(str(summary)) > 1500
                        else str(summary)
                    )
                    self.log(context, "SYSTEM", f"📊 [总结内容]:\n{display_summary}")
                    return {"messages": messages, "summary": summary}

                missing_files = [
                    f
                    for i, f in enumerate(target_files)
                    if not os.path.exists(check_paths[i])
                ]
                if not missing_files:
                    self.log(context, "SYSTEM", "✅ [验收通过] 所有目标文件均已生成！")
                    display_summary = (
                        str(summary)[:1500] + "..."
                        if len(str(summary)) > 1500
                        else str(summary)
                    )
                    self.log(context, "SYSTEM", f"📊 [总结内容]:\n{display_summary}")
                    return {"messages": messages, "summary": summary}

                error_count += 1
                if error_count >= MAX_ERRORS:
                    self.log(
                        context,
                        "ERROR",
                        f"❌ [验收失败] 连续 {error_count} 次未通过，挂起等待人工干预",
                    )
                    context.node_state[self.node_id] = NodeState.WAITING
                    raise asyncio.CancelledError(
                        f"连续失败，以下文件未生成: {missing_files}"
                    )

                self.log(
                    context,
                    "WARNING",
                    f"⚠️ [验收打回] 第 {error_count}/{MAX_ERRORS} 次，缺失文件: {missing_files}",
                )
                messages.append(
                    {
                        "role": "user",
                        "content": f"系统未检测到以下文件：{missing_files}。请确保使用工具将内容写入这些文件中！",
                    }
                )

        except asyncio.CancelledError:
            raise

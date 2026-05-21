import asyncio
import json
import os
from typing import Any, Dict

from src.harness.enums import NodeState
from src.harness.node.agent_node import AgentNode


class Node(AgentNode):
    """全能 Agent 循环：支持纯文本总结，也支持多文件强制验收"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "=" * 60)
        self.log(context, "SYSTEM", "🤖 [Agent循环] 节点启动")
        self.log(
            context,
            "SYSTEM",
            f"📥 [Agent循环] 收到输入包裹: {list(inputs.keys()) if inputs else '空'}",
        )

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
                    f"✅ [动态规则挂载] 成功加载动态校验指标: {list(self.task_done_info.keys())}",
                )
                self.log(
                    context,
                    "SYSTEM",
                    f"📋 [校验规则详情] {json.dumps(self.task_done_info, ensure_ascii=False)}",
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
                f"ℹ️ [动态规则] 未收到动态规则，使用默认配置: {self.task_done_info}",
            )

        my_memory = context.node_memory.setdefault(self.node_id, {})

        messages = my_memory.get("messages", inputs.get("messages", []))
        self.log(context, "SYSTEM", f"💬 [消息上下文] 当前消息数量: {len(messages)}")
        if messages:
            for i, msg in enumerate(messages[-3:]):
                role = msg.get("role", "unknown")
                content_preview = str(msg.get("content", ""))[:80]
                self.log(context, "SYSTEM", f"  📝 [{i}] {role}: {content_preview}...")

        pending_push = my_memory.pop("force_push", [])
        if pending_push:
            self.log(
                context, "SYSTEM", f"🔔 [人工指令] 收到 {len(pending_push)} 条人工指令"
            )
            for msg in pending_push:
                messages.append({"role": "user", "content": f"[人工指令] {msg}"})

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
                check_paths.append(
                    fpath.replace(
                        "/agent_vm",
                        os.path.join(
                            os.path.dirname(
                                os.path.dirname(
                                    os.path.dirname(
                                        os.path.dirname(os.path.abspath(__file__))
                                    )
                                )
                            ),
                            "agent_vm",
                        ),
                        1,
                    )
                )
        else:
            self.log(context, "SYSTEM", "📁 [文件验收] 无目标文件，将直接输出总结")

        tools = self.get_all_tools()
        self.log(context, "SYSTEM", f"🔧 [工具集] 可用工具数量: {len(tools)}")

        MAX_ERRORS = 3
        error_count = 0

        try:
            while True:
                self.log(context, "SYSTEM", "-" * 40)
                self.log(context, "SYSTEM", "🔄 [Agent循环] 开始新一轮思考...")

                loop_result = await self.run_agent_loop(context, messages, tools)
                messages = loop_result["messages"]
                summary = loop_result["summary"]

                if not check_paths:
                    self.log(
                        context, "SYSTEM", "✅ [任务完结] 无文件校验需求，输出总结。"
                    )
                    self.log(
                        context, "SYSTEM", f"📊 [总结内容] {str(summary)[:200]}..."
                    )
                    my_memory["messages"] = messages
                    return {"messages": messages, "summary": summary}

                missing_files = [
                    f
                    for i, f in enumerate(target_files)
                    if not os.path.exists(check_paths[i])
                ]
                if not missing_files:
                    self.log(context, "SYSTEM", "✅ [验收通过] 所有目标文件均已生成！")
                    self.log(
                        context, "SYSTEM", f"📊 [总结内容] {str(summary)[:200]}..."
                    )
                    my_memory["messages"] = messages
                    return {"messages": messages, "summary": summary}

                error_count += 1
                if error_count >= MAX_ERRORS:
                    self.log(
                        context,
                        "ERROR",
                        f"❌ [验收失败] 连续 {error_count} 次未通过，挂起等待人工干预",
                    )
                    my_memory["messages"] = messages
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
            my_memory["messages"] = messages
            raise

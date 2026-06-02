import asyncio
from typing import Any, Dict
from src.harness.enums import NodeState
from src.harness.node.agent_node import AgentNode


class Node(AgentNode):
    """人工干预节点：利用状态机优雅挂起，等待用户指令注入"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "⏸️ [人工干预] 节点启动，检查人类答复状态...")

        my_memory = context.node_memory.setdefault(self.node_id, {})
        force_push_msgs = my_memory.pop("force_push", [])

        if force_push_msgs:
            human_reply = force_push_msgs[-1]
            self.log(context, "SYSTEM", f"✅ [人工干预] 成功收到人类答复: {human_reply}")

            return {
                "human_reply": human_reply,
                "context_data": inputs.get("context_data")
            }

        prompt_message = self.config.get("prompt_message", "流程已暂停，请审查并输入您的指示：")
        context_data = inputs.get("context_data")

        if context_data:
            data_preview = str(context_data)[:200] + "..." if len(str(context_data)) > 200 else str(context_data)
            self.log(context, "SYSTEM", f"📄 [待审数据]: {data_preview}")

        self.log(context, "WARNING", f"✋ {prompt_message}")

        context.node_state[self.node_id] = NodeState.WAITING
        raise asyncio.CancelledError("已挂起，等待人类注入指令")
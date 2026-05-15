from typing import Any, Dict

from src.harness.node.base import BaseNode
from src.harness.utils.llm_helper import call_llm, inject_force_push
from src.harness.utils.tool_helper import get_system_schema


class Node(BaseNode):
    """大模型聊天节点"""

    async def execute(
        self, inputs: dict, force_push_msgs: list, context: Any
    ) -> Dict[str, Any]:
        messages = inputs.get("messages", [])

        messages = inject_force_push(messages, force_push_msgs)

        tools = get_system_schema()

        response, messages = await call_llm(
            model=context.model, messages=messages, tools=tools
        )

        return {"messages": messages, "response": response}

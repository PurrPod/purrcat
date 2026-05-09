from typing import Any, Dict
from harness.node.base import BaseNode
from harness.utils.llm_helper import call_llm, inject_force_push


class Node(BaseNode):
    """大模型聊天节点"""

    async def execute(self, inputs: dict, force_push_msgs: list, context: Any) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        
        # 注入强制推送的消息
        messages = inject_force_push(messages, force_push_msgs)
        
        tools = inputs.get("tools", [])

        # 调用 LLM 辅助函数
        response, messages = await call_llm(
            model=context.model,
            messages=messages,
            tools=tools,
            node_log_func=self.log,
            context=context
        )

        return {"default": messages, "response": response}

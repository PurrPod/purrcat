from typing import Any, Dict
from src.harness.node.base import BaseNode
from src.harness.utils.llm_helper import call_llm, inject_force_push


class Node(BaseNode):
    """大模型聊天节点"""

    async def execute(
        self, inputs: dict, force_push_msgs: list, context: Any
    ) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        messages = inject_force_push(messages, force_push_msgs)
        tools = self.get_all_tools()

        self.log(context, "SYSTEM", f"🧠 [LLM对话] 请求发起，输入消息数: {len(messages)}")
        response, messages = await call_llm(
            model=context.model, messages=messages, tools=tools
        )
        self.log(context, "SYSTEM", f"✅ [LLM对话] 请求完成，当前消息数: {len(messages)}")

        outputs = {"messages": messages, "response": response}
        self.save_checkpoints(context, {"inputs": inputs, "outputs": {"messages": messages}})
        return outputs

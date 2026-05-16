from typing import Any, Dict

from src.harness.node.agent_node import AgentNode
from src.harness.utils.llm_helper import inject_force_push


class Node(AgentNode):
    """总结输出循环节点：封装思考->调用工具->总结的完整循环逻辑"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        tools = self.get_all_tools()

        if force_push_msgs:
            messages = inject_force_push(messages, force_push_msgs)

        # 没有特殊校验，大模型说 task_done 就算结束
        final_outputs = await self.run_agent_loop(context, messages, tools)

        self.save_checkpoints(context, {"inputs": inputs, "outputs": final_outputs})
        return final_outputs

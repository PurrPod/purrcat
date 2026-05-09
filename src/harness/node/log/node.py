from typing import Dict, Any
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """日志节点：输出日志信息"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        previous_info = inputs.get("previous_info")
        log_content = inputs.get("log_content") or self.config.get("log_content", "")

        if hasattr(context, "log_and_notify"):
            context.log_and_notify("SYSTEM", log_content)

        return {
            "success": True,
            "default": previous_info
        }
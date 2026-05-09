from typing import Dict, Any
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """列表截断器：截取列表的指定范围"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        msg_list = inputs.get("list", [])
        start = inputs.get("start_int") or self.config.get("start_int", 0)
        end = inputs.get("end_int") or self.config.get("end_int", len(msg_list))
        truncated_list = list(msg_list)[start:end]
        return {"default": truncated_list}
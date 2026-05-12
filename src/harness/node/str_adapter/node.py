from typing import Dict, Any
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """字符串适配器节点：将两个字符串拼接"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        str1 = inputs.get("str1") or self.config.get("str1", "")
        str2 = inputs.get("str2") or self.config.get("str2", "")
        return {"concatenated_string": str1 + str2}

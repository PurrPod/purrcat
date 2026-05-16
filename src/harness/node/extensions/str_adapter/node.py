from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """字符串适配器节点：将两个字符串拼接"""

    async def execute(
        self, inputs: Dict[str, Any], force_push_msgs: list, context: Any
    ) -> Dict[str, Any]:
        str1 = inputs.get("str1") or self.config.get("str1", "")
        str2 = inputs.get("str2") or self.config.get("str2", "")

        result = str1 + str2

        self.log(context, "SYSTEM", f"🔤 [字符串拼接] 产出长度为 {len(result)} 的字符串。")

        outputs = {"concatenated_string": result}
        self.save_checkpoints(context, {"inputs": inputs, "outputs": outputs})
        return outputs

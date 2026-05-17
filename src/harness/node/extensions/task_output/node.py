from typing import Any, Dict

from src.harness.node.base import BaseNode


class Node(BaseNode):
    """全局输出节点：收集上游的连线数据，并写入 Task 的全局 outputs 中"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        for key, value in inputs.items():
            context.outputs[key] = value

        self.log(
            context,
            "SYSTEM",
            f"📤 [引擎出口] DAG流转结束！最终收集到的全局参数: {list(inputs.keys())}",
        )

        return {"default": True}

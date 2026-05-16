from typing import Any, Dict

from src.harness.node.base import BaseNode


class Node(BaseNode):
    """全局输入节点：读取 Task 初始化时传入的全局 inputs 参数，并作为输出暴露给下游"""

    async def execute(
        self, inputs: Dict[str, Any], force_push_msgs: list, context: Any
    ) -> Dict[str, Any]:
        self.log(context, "SYSTEM", f"📥 [引擎入口] 获取到全局启动参数，键值: {list(context.inputs.keys())}")

        # 记录落盘
        self.save_checkpoints(context, {"inputs": {}, "outputs": context.inputs})

        return context.inputs

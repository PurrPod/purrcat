from typing import Any, Dict
import json

from src.harness.node.base import BaseNode


class Node(BaseNode):
    """全局输入节点：读取 Task 初始化时传入的全局 inputs 参数，并作为输出暴露给下游"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "🚪 [全局输入] 接收到任务启动参数：")

        safe_inputs = {}
        for k, v in context.inputs.items():
            safe_inputs[k] = str(v)[:500] + "..." if len(str(v)) > 500 else v
        self.log(
            context,
            "SYSTEM",
            f"{json.dumps(safe_inputs, indent=2, ensure_ascii=False)}",
        )

        return context.inputs

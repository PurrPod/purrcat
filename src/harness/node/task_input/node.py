from typing import Dict, Any
from harness.node.base import BaseNode

class Node(BaseNode):
    """全局输入节点：读取 Task 初始化时传入的全局 inputs 参数，并作为输出暴露给下游"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        # 直接将引擎传入的全局入参作为自己的输出流下发
        # 例如 context.inputs 为 {"prompt": "写个贪吃蛇", "github_url": "..."}
        # 那么连线可以通过 sourceHandle="prompt" 拿到对应的值
        
        self.log(context, "SYSTEM", f"📥 获取到全局输入参数: {list(context.inputs.keys())}")
        
        # 将整个 inputs 字典作为输出返回
        return context.inputs
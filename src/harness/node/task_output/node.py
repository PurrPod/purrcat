from typing import Dict, Any
from src.harness.node.base import BaseNode

class Node(BaseNode):
    """全局输出节点：收集上游的连线数据，并写入 Task 的全局 outputs 中"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        # inputs 里面包含了上游连线传过来的所有数据
        # 例如: {"final_messages": [...], "task_summary": "..."}
        
        for key, value in inputs.items():
            context.outputs[key] = value
            
        self.log(context, "SYSTEM", f"📤 全局输出已就绪，最终打包字段: {list(inputs.keys())}")
        
        return {"default": True}
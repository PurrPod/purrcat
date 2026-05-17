from typing import Any, Dict

from src.harness.node.base import BaseNode


class Node(BaseNode):
    """全局输入节点：读取 Task 初始化时传入的全局 inputs 参数，并作为输出暴露给下游"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "=" * 50)
        self.log(context, "SYSTEM", "🚪 [全局输入] 节点启动 (工作流入口)")
        
        global_vars = self.config.get("global_vars", [])
        self.log(context, "SYSTEM", f"📋 [全局输入] 配置的全局变量: {[v.get('name') if isinstance(v, dict) else v for v in global_vars]}")

        self.log(context, "SYSTEM", f"📥 [全局输入] 收到外部启动参数，键值: {list(context.inputs.keys())}")
        
        for key, val in context.inputs.items():
            val_preview = str(val)[:100] + "..." if len(str(val)) > 100 else str(val)
            self.log(context, "SYSTEM", f"  🔹 {key} = {val_preview}")

        self.log(context, "SYSTEM", f"📤 [全局输入] 暴露 {len(context.inputs)} 个变量给下游节点")
        
        return context.inputs

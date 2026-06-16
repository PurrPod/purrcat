import sys
import traceback
from typing import Any, Dict
from src.harness.node.base import BaseNode

class Node(BaseNode):
    """Python 脚本执行器：在受限命名空间内执行自定义代码处理数据"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "🐍 [Python Runner] 节点启动，准备执行代码...")
        
        code = self.config.get("code", "")
        if not code.strip():
            self.log(context, "WARNING", "⚠️ [Python Runner] 代码为空。")
            return {}

        local_namespace = {
            "inputs": inputs,
            "outputs": {}
        }
        
        try:
            exec(code, {"__builtins__": __builtins__}, local_namespace)
            outputs = local_namespace.get("outputs", {})
            self.log(context, "SYSTEM", f"✅ [Python Runner] 执行成功，提取了 {len(outputs)} 个输出变量。")
            return outputs
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            self.log(context, "ERROR", f"❌ [Python Runner] 脚本执行崩溃:\n{error_msg}")
            raise RuntimeError(f"Python 脚本执行失败: {e}")
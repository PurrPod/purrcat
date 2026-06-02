from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """环境变量加载器：直接从当前 Task 内存中的图谱配置 (graph['env']) 提取变量"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "🌐 [环境变量] 节点启动")

        env_data = context.graph.get("env", {})

        if not env_data:
            self.log(context, "WARNING", "⚠️ [环境变量] 当前图谱 JSON 中没有配置 'env' 键，或者环境为空。")

        exposed_keys = self.config.get("exposed_keys", [])
        outputs = {}
        exposed_count = 0

        for item in exposed_keys:
            if not isinstance(item, dict):
                continue

            key_name = item.get("name")
            if not key_name:
                continue

            val = env_data.get(key_name)
            outputs[key_name] = val

            val_str = str(val)
            if "KEY" in key_name.upper() or "TOKEN" in key_name.upper() or "SECRET" in key_name.upper():
                val_preview = val_str[:4] + "***" + val_str[-4:] if len(val_str) > 8 else "***"
            else:
                val_preview = val_str[:40] + "..." if len(val_str) > 40 else val_str

            self.log(context, "SYSTEM", f"  🔹 成功提取并暴露 [{key_name}] = {val_preview}")
            exposed_count += 1

        self.log(context, "SYSTEM", f"✅ [环境变量] 分发完成，共输出 {exposed_count} 个变量至下游链路")

        return outputs
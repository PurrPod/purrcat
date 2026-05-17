import json
from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """JSON 构建器：将用户配置的键值对及上游连线输入打包为 JSON 字符串"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", f"📥 [JSON构建] 收到输入包裹: {list(inputs.keys()) if inputs else '空'}")

        result_dict = {}

        kv_pairs = self.config.get("kv_pairs", [])
        self.log(context, "SYSTEM", f"📋 [JSON构建] 配置的键值对列表: {[item.get('name') for item in kv_pairs if isinstance(item, dict) and item.get('name')]}")

        for item in kv_pairs:
            if not isinstance(item, dict):
                continue

            key_name = item.get("name")
            if not key_name:
                continue

            if key_name in inputs and inputs[key_name] is not None:
                val = inputs[key_name]
                source = "连线输入"
            else:
                val = item.get("value", "")
                source = "手动配置"

            result_dict[key_name] = val
            val_preview = str(val)[:100] + "..." if len(str(val)) > 100 else str(val)
            self.log(context, "SYSTEM", f"  🔹 [{key_name}] = {val_preview} (来源: {source})")

        self.log(context, "SYSTEM", f"📦 [JSON构建] 成功打包 {len(result_dict)} 个键值对")

        try:
            json_string = json.dumps(result_dict, ensure_ascii=False)
            self.log(context, "SYSTEM", f"📤 [JSON构建] 输出 JSON (长度 {len(json_string)}): {json_string[:200]}{'...' if len(json_string) > 200 else ''}")
        except TypeError as e:
            self.log(context, "ERROR", f"❌ [JSON构建] 字典中包含无法序列化的对象，尝试强转字符串: {e}")
            json_string = str(result_dict)

        return {"json_string": json_string}

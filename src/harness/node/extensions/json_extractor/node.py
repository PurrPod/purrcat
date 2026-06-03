import json
from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """JSON 提取器：根据用户配置的 keys，从输入的字典中提取特定字段作为动态引脚输出"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "🔍 [JSON提取] 节点启动")

        raw_data = inputs.get("data")

        data_dict = {}
        if isinstance(raw_data, str):
            try:
                data_dict = json.loads(raw_data)
            except json.JSONDecodeError:
                self.log(
                    context,
                    "WARNING",
                    "⚠️ [JSON提取] 传入的数据不是合法的 JSON 字符串，将按空字典处理",
                )
        elif isinstance(raw_data, dict):
            data_dict = raw_data
        else:
            self.log(
                context,
                "WARNING",
                f"⚠️ [JSON提取] 不支持的数据类型: {type(raw_data)}，需要 dict 或 json 字符串",
            )

        extract_keys = self.config.get("extract_keys", [])

        outputs = {}
        extracted_count = 0

        for item in extract_keys:
            if not isinstance(item, dict):
                continue

            key_name = item.get("name")
            if not key_name:
                continue

            val = data_dict.get(key_name)
            outputs[key_name] = val

            val_preview = str(val)[:50] + "..." if len(str(val)) > 50 else str(val)
            self.log(context, "SYSTEM", f"  ✂️ 提取 [{key_name}] = {val_preview}")
            extracted_count += 1

        self.log(
            context,
            "SYSTEM",
            f"✅ [JSON提取] 完成，共提取了 {extracted_count} 个字段分配给下游",
        )

        return outputs

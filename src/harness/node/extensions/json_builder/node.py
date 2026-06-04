import json
from typing import Any, Dict

from src.harness.node.base import BaseNode


class Node(BaseNode):
    """JSON 构建器：将用户配置的键值对及上游连线输入打包为 JSON 字符串"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        result_dict = {}

        kv_pairs = self.config.get("kv_pairs", [])

        for item in kv_pairs:
            if not isinstance(item, dict):
                continue

            key_name = item.get("name")
            if not key_name:
                continue

            if key_name in inputs and inputs[key_name] is not None:
                val = inputs[key_name]
            else:
                val = item.get("value", "")

            result_dict[key_name] = val

        self.log(
            context, "SYSTEM", f"📦 [JSON构建] 成功打包 {len(result_dict)} 个键值对"
        )

        try:
            json_string = json.dumps(result_dict, ensure_ascii=False, indent=2)
            display_json = json_string[:1500] + "\n...[内容过长已截断]" if len(json_string) > 1500 else json_string
            self.log(context, "SYSTEM", f"📤 [JSON构建] 输出:\n{display_json}")
        except TypeError as e:
            self.log(
                context,
                "ERROR",
                f"❌ [JSON构建] 字典中包含无法序列化的对象: {e}",
            )
            json_string = str(result_dict)

        return {"json_string": json.dumps(result_dict, ensure_ascii=False)}

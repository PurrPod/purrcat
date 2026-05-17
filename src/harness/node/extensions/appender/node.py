from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """列表追加器：将 append_list 追加到 base_list 后面"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        base_list = inputs.get("base_list", [])
        append_list = inputs.get("append_list", [])

        result_list = list(base_list) if base_list else []

        if append_list:
            if isinstance(append_list, list):
                result_list.extend(append_list)
            else:
                self.log(context, "WARNING", f"⚠️ [列表追加] append_list 非列表类型，强制放入追加。")
                result_list.append(append_list)

        self.log(context, "SYSTEM", f"🔗 [列表追加] 合并后长度: {len(result_list)}")

        return {"merged_list": result_list}
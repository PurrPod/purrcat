from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """列表追加器：将 append_list 追加到 base_list 后面"""

    async def execute(
        self, inputs: Dict[str, Any], force_push_msgs: list, context: Any
    ) -> Dict[str, Any]:
        base_list = inputs.get("base_list", [])
        append_list = inputs.get("append_list", [])

        result_list = list(base_list) if base_list else []

        if append_list and isinstance(append_list, list):
            result_list.extend(append_list)

        self.log(context, "SYSTEM", f"🔗 [列表追加] 基础长度: {len(base_list or [])}，追加长度: {len(append_list or [])}，合并后: {len(result_list)}")

        outputs = {"merged_list": result_list}
        self.save_checkpoints(context, {"inputs": inputs, "outputs": outputs})
        return outputs

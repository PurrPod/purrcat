from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """列表截断器：截取列表的指定范围"""

    async def execute(
        self, inputs: Dict[str, Any], force_push_msgs: list, context: Any
    ) -> Dict[str, Any]:
        msg_list = inputs.get("list", [])
        start = inputs.get("start_int") or self.config.get("start_int", 0)
        end = inputs.get("end_int") or self.config.get("end_int", len(msg_list))
        truncated_list = list(msg_list)[start:end]

        self.log(context, "SYSTEM", f"✂️ [列表截断] 索引 {start} 到 {end}，截断前长度: {len(msg_list)}，截断后长度: {len(truncated_list)}")

        outputs = {"truncated_list": truncated_list}
        self.save_checkpoints(context, {"inputs": inputs, "outputs": outputs})
        return outputs

from typing import Dict, Any
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """消息卡片构建器：将文本和角色包装成标准 MessageList"""

    async def execute(
        self, inputs: Dict[str, Any], force_push_msgs: list, context: Any
    ) -> Dict[str, Any]:
        content = inputs.get("content") or self.config.get("content", "")
        role = inputs.get("role") or self.config.get("role", "user")

        if not content:
            return {"message_list": []}

        return {"message_list": [{"role": role, "content": content}]}

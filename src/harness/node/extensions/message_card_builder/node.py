import json
from typing import Any, Dict

from src.harness.node.base import BaseNode


class Node(BaseNode):
    """消息卡片构建器：把文本包装成 role=user、type=workflow_input 的消息卡片"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "💬 [消息构建] 开始执行")

        content = self.unpack(inputs, "content")

        if not content:
            self.log(context, "WARNING", "⚠️ [消息构建] 收到空内容，返回空列表。")
            return {"message_list": []}

        message = {
            "role": "user",
            "content": json.dumps(
                {"type": "workflow_input", "content": content}, ensure_ascii=False
            ),
        }
        self.log(
            context,
            "SYSTEM",
            f"📤 [消息构建] 输出消息卡片:\n{content[:1500]}{'...' if len(content) > 1500 else ''}",
        )

        return {"message_list": [message]}

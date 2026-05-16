from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """消息卡片构建器：将文本和角色包装成标准 MessageList"""

    async def execute(
        self, inputs: Dict[str, Any], force_push_msgs: list, context: Any
    ) -> Dict[str, Any]:
        content = inputs.get("content") or self.config.get("content", "")
        role = inputs.get("role") or self.config.get("role", "user")

        if not content:
            self.log(context, "WARNING", "⚠️ [消息构建] 收到空内容，返回空列表。")
            outputs = {"message_list": []}
        else:
            self.log(context, "SYSTEM", f"📝 [消息构建] 构建 {role} 角色卡片，内容长度: {len(content)}")
            outputs = {"message_list": [{"role": role, "content": content}]}

        self.save_checkpoints(context, {"inputs": inputs, "outputs": outputs})
        return outputs

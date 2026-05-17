from typing import Any, Dict

from src.harness.node.base import BaseNode


class Node(BaseNode):
    """消息卡片构建器：将文本和角色包装成标准 MessageList"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "=" * 50)
        self.log(context, "SYSTEM", "💬 [消息构建] 节点启动")
        self.log(
            context,
            "SYSTEM",
            f"📥 [消息构建] 收到输入包裹: {list(inputs.keys()) if inputs else '空'}",
        )

        content = inputs.get("content") or self.config.get("content", "")
        role = inputs.get("role") or self.config.get("role", "user")

        self.log(context, "SYSTEM", f"🎭 [消息构建] 角色: {role}")

        if not content:
            self.log(context, "WARNING", "⚠️ [消息构建] 收到空内容，返回空列表。")
            return {"message_list": []}

        content_preview = content[:150] + "..." if len(content) > 150 else content
        self.log(
            context,
            "SYSTEM",
            f"📝 [消息构建] 内容 (长度 {len(content)}): {content_preview}",
        )

        message = {"role": role, "content": content}
        self.log(
            context,
            "SYSTEM",
            f"📤 [消息构建] 输出消息卡片: role={role}, content_length={len(content)}",
        )

        return {"message_list": [message]}

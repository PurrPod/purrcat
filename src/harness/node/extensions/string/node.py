from typing import Any, Dict

from src.harness.node.base import BaseNode


class Node(BaseNode):
    """静态字符串字面量节点：把面板输入框内容作为 string 信封输出"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        value = self.config.get("value", "")
        if not isinstance(value, str):
            value = str(value)

        self.log(
            context,
            "SYSTEM",
            f"📝 [字符串] 输出 {len(value)} 字符: {value[:60]}{'...' if len(value) > 60 else ''}",
        )
        return {"text": self.pack(value, "string", "text/plain")}

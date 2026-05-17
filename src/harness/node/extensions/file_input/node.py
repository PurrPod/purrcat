import os
from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """文件输入节点：读取文件内容"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        file_path = inputs.get("file_path") or self.config.get("file_path", "")

        if not file_path:
            self.log(context, "ERROR", "❌ [文件读取] 缺失 file_path 参数")
            raise ValueError("FileInputNode 缺失 file_path 参数")

        if not os.path.exists(file_path):
            self.log(context, "ERROR", f"❌ [文件读取] 文件不存在: {file_path}")
            raise FileNotFoundError(f"文件不存在: {file_path}")

        self.log(context, "SYSTEM", f"📖 [文件读取] 正在读取文件: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.log(context, "SYSTEM", f"✅ [文件读取] 成功读取，内容长度: {len(content)}")

        return {"file_content": content}

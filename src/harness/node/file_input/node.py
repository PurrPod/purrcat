import os
from typing import Dict, Any
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """文件输入节点：读取文件内容"""

    async def execute(
        self, inputs: Dict[str, Any], force_push_msgs: list, context: Any
    ) -> Dict[str, Any]:
        file_path = inputs.get("file_path") or self.config.get("file_path", "")

        if not file_path:
            raise ValueError("FileInputNode 缺失 file_path 参数")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return {"file_content": content}

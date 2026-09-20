import json
import os
from typing import Any, Dict

from src.harness import envelope
from src.harness.enums import LogType
from src.harness.node.base import BaseNode

# 扩展名 → mime（用于 fallback）
_EXT_MIME = {
    ".html": "text/html",
    ".htm": "text/html",
    ".svg": "image/svg+xml",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _mime_to_kind(mime: str) -> str:
    """mime → 前端渲染分支"""
    if not mime:
        return "text"
    if mime == "application/pdf":
        return "pdf"
    if mime == "image/svg+xml":
        return "svg"
    if mime.startswith("image/"):
        return "image"
    if mime == "text/html":
        return "html"
    return "text"


class Node(BaseNode):
    """文件落盘：将 string 内容写入本节点 files/ 目录，输出 file 信封供下游消费。"""

    def _emit_artifact(self, context: Any, kind: str, uri: str, mime: str):
        payload = json.dumps({"kind": kind, "uri": uri, "mime": mime}, ensure_ascii=False)
        self.log(context, LogType.ARTIFACT, payload)

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "💾 [文件落盘] 节点启动")

        content = self.unpack(inputs, "content")
        if content is None:
            raise ValueError("文件落盘节点缺少 [content] 输入")
        if not isinstance(content, str):
            content = str(content)

        filename = self.unpack(inputs, "filename") or "output.txt"
        filename = str(filename).strip() or "output.txt"

        _, ext = os.path.splitext(filename)
        mime = _EXT_MIME.get(ext.lower(), "text/plain")

        file_env = self.file_env(context, filename, content, mime)
        kind = _mime_to_kind(mime)
        self.log(context, "SYSTEM", f"📝 [落盘] 已写入 {filename} ({mime})")
        self._emit_artifact(context, kind, file_env["data"], mime)
        return {"file": file_env}
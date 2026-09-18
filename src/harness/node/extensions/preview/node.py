import json
import os
from typing import Any, Dict, Optional

from src.harness import envelope
from src.harness.enums import LogType
from src.harness.node.base import BaseNode

import markdown

# 扩展名 → mime
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


def _sniff_string_mime(text: str) -> str:
    """string 内容嗅探 mime"""
    stripped = text.lstrip()[:200].lower()
    if stripped.startswith("<!doctype html") or stripped.startswith("<html"):
        return "text/html"
    if stripped.startswith("<?xml") and "<svg" in stripped:
        return "image/svg+xml"
    if stripped.startswith("<svg"):
        return "image/svg+xml"
    return "text/markdown"


def _wrap_markdown_html(content: str, title: str) -> str:
    """Markdown / 纯文本 → 带样式的完整 HTML 页面"""
    try:
        html_content = markdown.markdown(
            str(content), extensions=["tables", "fenced_code"]
        )
    except Exception:
        html_content = f"<pre>{content}</pre>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 2rem; background: #fdfaf5; }}
        h1 {{ border-bottom: 2px solid #D47A5A; padding-bottom: 0.5rem; color: #1a1a1a; }}
        pre {{ background: #1a1a1a; color: #fdfaf5; padding: 1rem; border-radius: 8px; overflow-x: auto; }}
        code {{ background: #e9ecef; padding: 0.2rem 0.4rem; border-radius: 4px; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="content">
        {html_content}
    </div>
</body>
</html>"""


class Node(BaseNode):
    """预览看板：string/file 输入按 mime 渲染，string 落盘，输出统一 file 信封"""

    def _emit_artifact(self, context: Any, kind: str, uri: str, mime: str, title: str):
        """推送结构化 ARTIFACT 日志（前端按 kind 分支渲染）"""
        payload = json.dumps(
            {"kind": kind, "uri": uri, "mime": mime, "title": title},
            ensure_ascii=False,
        )
        self.log(context, LogType.ARTIFACT, payload)

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "🖼️ [预览] 节点启动")
        title = self.config.get("title", "Preview")

        env = self.unpack_env(inputs, "source")
        if env is None:
            raise ValueError("预览节点缺少 [source] 输入")

        env = envelope.coerce(env, ["string", "file"])
        env_type = env.get("type")

        if env_type == "file":
            return self._handle_file(env, context, title)

        # string 输入：嗅探 mime 并落盘为文件
        return await self._handle_string(env, context, title)

    def _handle_file(self, env: dict, context: Any, title: str) -> Dict[str, Any]:
        """file 输入：补全 mime 后透传引用"""
        uri = env.get("data")
        if not isinstance(uri, str) or not uri:
            raise ValueError("file 信封缺少有效的 data (URI)")

        mime = env.get("mime")
        if not mime:
            # 按扩展名补全
            _, ext = os.path.splitext(str(uri))
            mime = _EXT_MIME.get(ext.lower(), "application/octet-stream")

        kind = _mime_to_kind(mime)
        self.log(context, "SYSTEM", f"📎 [预览] 透传文件引用: {uri} ({mime})")
        self._emit_artifact(context, kind, uri, mime, title)

        out = envelope.make("file", uri, mime, env.get("meta"))
        return {"file": out}

    async def _handle_string(self, env: dict, context: Any, title: str) -> Dict[str, Any]:
        """string 输入：嗅探内容类型，落盘到本节点 files/ 并输出 file 信封"""
        text = env.get("data")
        if not isinstance(text, str):
            text = str(text)

        mime = _sniff_string_mime(text)
        kind = _mime_to_kind(mime)

        if mime == "text/markdown":
            # Markdown / 纯文本包装为带样式的 HTML 看板
            full_html = _wrap_markdown_html(text, title)
            fname, mime, kind = "preview.html", "text/html", "html"
            file_env = self.file_env(context, fname, full_html, mime)
        elif mime == "text/html":
            fname = "preview.html"
            file_env = self.file_env(context, fname, text, mime)
        elif mime == "image/svg+xml":
            fname = "preview.svg"
            file_env = self.file_env(context, fname, text, mime)
        else:
            fname = "preview.txt"
            mime, kind = "text/plain", "text"
            file_env = self.file_env(context, fname, text, mime)

        self.log(context, "SYSTEM", f"💾 [预览] string 已落盘为 {fname} ({mime})")
        self._emit_artifact(context, kind, file_env["data"], mime, title)
        return {"file": file_env}

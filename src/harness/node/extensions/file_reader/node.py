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


# 文本类 mime（能从磁盘读回字符串内容作为 content 输出）
_TEXT_KINDS = {"text", "html", "svg"}


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


def _wrap_markdown_html(content: str) -> str:
    """Markdown / 纯文本 → 带样式的完整 HTML 页面（无标题，文件管理器预览风格）"""
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
    <title>Preview</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 2rem; background: #fdfaf5; }}
        pre {{ background: #1a1a1a; color: #fdfaf5; padding: 1rem; border-radius: 8px; overflow-x: auto; }}
        code {{ background: #e9ecef; padding: 0.2rem 0.4rem; border-radius: 4px; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="content">
        {html_content}
    </div>
</body>
</html>"""


class Node(BaseNode):
    """文件读取/预览：string/file 输入按 mime 渲染，并透出文件文本（content）。

    - file 输入：读回文本作为 content 输出，同时保留 file 引用输出；预览走 URI（前端 /artifact 渲染）。
    - string 输入：不落盘，内容以 content 输出；预览以内联 content 交给前端渲染。
    """

    def _emit_artifact(
        self,
        context: Any,
        kind: str,
        mime: str,
        uri: str = None,
        content: str = None,
        name: str = None,
    ):
        """推送结构化 ARTIFACT 日志（前端按 kind/uri 或内联 content 渲染）"""
        payload: Dict[str, Any] = {"kind": kind, "mime": mime}
        if uri:
            payload["uri"] = uri
        if content is not None:
            payload["content"] = content
        if name:
            payload["name"] = name
        self.log(context, LogType.ARTIFACT, json.dumps(payload, ensure_ascii=False))

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "📖 [文件读取/预览] 节点启动")

        env = self.unpack_env(inputs, "source")
        if env is None:
            raise ValueError("文件读取节点缺少 [source] 输入")

        env = envelope.coerce(env, ["string", "file"])
        env_type = env.get("type")

        if env_type == "file":
            return self._handle_file(env, context)
        return self._handle_string(env, context)

    def _handle_file(self, env: dict, context: Any) -> Dict[str, Any]:
        """file 输入：尽量读回文本，保留文件引用，预览走 URI 透传"""
        uri = env.get("data")
        if not isinstance(uri, str) or not uri:
            raise ValueError("文件信封缺少有效的 data (URI)")

        mime = env.get("mime")
        if not mime:
            _, ext = os.path.splitext(str(uri))
            mime = _EXT_MIME.get(ext.lower(), "application/octet-stream")
        kind = _mime_to_kind(mime)

        text: Optional[str] = None
        path = envelope.parse_uri(uri, checkpoint_dir=context.checkpoint_dir)
        if path and path.is_file() and kind in _TEXT_KINDS:
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                text = None

        name = os.path.basename(str(uri))
        self.log(context, "SYSTEM", f"📎 [读取] {uri} ({mime})")
        self._emit_artifact(context, kind, mime, uri=uri, name=name)

        out = envelope.make("file", uri, mime, env.get("meta"))
        return {"content": text, "file": out}

    def _handle_string(self, env: dict, context: Any) -> Dict[str, Any]:
        """string 输入：不落盘；输出 content，预览以内联 HTML 交给前端"""
        text = env.get("data")
        if not isinstance(text, str):
            text = str(text)

        mime = _sniff_string_mime(text)

        if mime == "text/markdown":
            html = _wrap_markdown_html(text)
            render_mim, render_kind = "text/html", "html"
        elif mime == "image/svg+xml":
            html, render_mim, render_kind = text, mime, "svg"
        else:  # text/html
            html, render_mim, render_kind = text, mime, "html"

        self._emit_artifact(context, render_kind, render_mim, content=html)
        return {"content": text}

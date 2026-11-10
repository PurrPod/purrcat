"""工具多媒体的落盘与 vision 直注转换。

落盘目录由调用方传入，便于测试与配置注入。
"""

from __future__ import annotations

import base64
import mimetypes
import os
import time
import uuid
from typing import Any

# 图片扩展名集合：vision 直注时据此判断媒体是否为图片
# （OpenAI 兼容接口仅接受 webp/png/jpeg/gif，SVG/BMP 等走落盘路径）
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

SUPPORTED_MEDIA_TYPES = (
    "image",
    "video",
    "audio",
    "pdf",
    "mcp_media",
    "media_url",
    "media_base64",
)


def is_openai_content_parts(data: Any) -> bool:
    """判断 data 是否为 OpenAI 多模态 content parts 列表（vision 直注结果的特征签名）"""
    return (
        isinstance(data, list)
        and bool(data)
        and all(
            isinstance(p, dict) and p.get("type") in ("text", "image_url") for p in data
        )
    )


def image_data_url(base64_str: str, ext: str, mime_type: str | None = None) -> str:
    """图片 base64 → data URL；mcp_media 场景直接用工具给的 mimeType"""
    if not mime_type:
        mime_type = mimetypes.guess_type(f"file{ext}")[0] or "image/png"
    return f"data:{mime_type};base64,{base64_str}"


def build_vision_inline_parts(
    media_type: str, content_data: dict, tool_name: str
) -> list | None:
    """把工具输出的图片字典构造为 OpenAI 多模态 content parts。

    仅处理图片（视频/音频/PDF 仍走落盘路径）；返回 None 表示该媒体不适用直注。
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    marker_id = uuid.uuid4().hex[:8]

    if media_type == "image":
        ext = content_data.get("ext", ".png")
        if ext not in IMAGE_EXTS:
            return None
        data_url = image_data_url(content_data["data"], ext)
    elif media_type == "mcp_media":
        mime_type = str(content_data.get("mimeType", ""))
        ext = mimetypes.guess_extension(mime_type) or ""
        # SVG（image/svg+xml）等矢量/非常规格式 API 不接受，按扩展名白名单拦截
        if ext not in IMAGE_EXTS:
            return None
        data_url = image_data_url(content_data["data"], ext, mime_type)
    elif media_type == "media_base64":
        ext = content_data.get("ext", ".bin")
        if ext not in IMAGE_EXTS:
            return None
        data_url = image_data_url(content_data["data"], ext)
    elif media_type == "media_url":
        ext = content_data.get("ext", ".bin")
        if ext not in IMAGE_EXTS:
            return None
        import urllib.request

        with urllib.request.urlopen(content_data["url"], timeout=60) as r:
            raw = r.read()
        data_url = image_data_url(base64.b64encode(raw).decode("utf-8"), ext)
    else:
        return None

    # 占位路径仅供前端/模型引用展示，文件本体并未写入磁盘
    placeholder_name = f"vision_{tool_name}_{timestamp}_{marker_id}{ext}"
    text_part = {
        "type": "text",
        "text": (
            "🖼️ [vision直注] 图片未落盘，已直接注入本轮对话。\n"
            f"📂 占位路径: /agent_vm/.buffer/{placeholder_name}"
        ),
    }
    image_part = {"type": "image_url", "image_url": {"url": data_url}}
    return [text_part, image_part]


def _save_binary(buffer_dir: str, filename: str, data: str) -> str:
    filepath = os.path.join(buffer_dir, filename)
    with open(filepath, "wb") as f:
        f.write(base64.b64decode(data))
    return filepath


def _save_url(buffer_dir: str, filename: str, url: str) -> str:
    import shutil
    import urllib.request

    filepath = os.path.join(buffer_dir, filename)
    # 🌟 带超时的流式下载（urlretrieve 无超时，卡死时同样无法打断）
    with urllib.request.urlopen(url, timeout=60) as r, open(filepath, "wb") as f:
        shutil.copyfileobj(r, f)
    return filepath


def handle_media_content(
    content_data: Any,
    tool_name: str,
    *,
    buffer_dir: str,
    vision_mode: bool = False,
) -> Any:
    """处理多媒体内容：图片在 vision 模式下直注，其余落盘为路径提示。"""
    if not isinstance(content_data, dict):
        return content_data

    media_type = content_data.get("type")
    if media_type not in SUPPORTED_MEDIA_TYPES:
        return content_data

    if vision_mode:
        inline_parts = build_vision_inline_parts(media_type, content_data, tool_name)
        if inline_parts is not None:
            return inline_parts
        # 非图片（视频/音频/PDF 等）继续走原有落盘路径

    os.makedirs(buffer_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    marker_id = uuid.uuid4().hex[:8]

    try:
        if media_type == "media_url":
            ext = content_data.get("ext", ".bin")
            filename = f"{tool_name}_{timestamp}_{marker_id}{ext}"
            filepath = _save_url(buffer_dir, filename, content_data["url"])

        elif media_type in ("image", "video", "audio", "pdf", "mcp_media"):
            ext = content_data.get("ext", ".bin")
            if media_type == "mcp_media":
                mime_type = content_data.get("mimeType", ".bin")
                ext = (
                    ".png"
                    if mime_type.startswith("image/")
                    else mimetypes.guess_extension(mime_type) or ".bin"
                )
            filename = f"{tool_name}_{timestamp}_{marker_id}{ext}"
            filepath = _save_binary(buffer_dir, filename, content_data["data"])

        else:  # media_base64
            ext = content_data.get("ext", ".bin")
            filename = f"{tool_name}_{timestamp}_{marker_id}{ext}"
            filepath = _save_binary(buffer_dir, filename, content_data["data"])

        sandbox_path = f"/agent_vm/.buffer/{filename}"
        media_desc = {
            "image": "🖼️ 图片",
            "video": "📹 视频",
            "audio": "🎵 音频",
            "pdf": "📄 PDF",
            "mcp_media": "📦 媒体",
            "media_url": "🔗 下载文件",
            "media_base64": "📦 Base64 文件",
        }.get(media_type, "📦 文件")

        return (
            f"{media_desc}已成功保存至本地:\n"
            f"📂 宿主机路径: {filepath}\n"
            f"🐳 沙盒内路径: {sandbox_path}"
        )

    except Exception as e:
        print(f"⚠️ [多媒体处理异常] {e}")
        return content_data

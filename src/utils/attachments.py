"""会话图片附件：Task 视觉直注落副本，历史只存副本路径，发送前再还原 base64。

Task 的 vision 直注会把图片编码成 data URL 直接注入对话，落盘后一张 1MB 的图
会膨胀成约 1.4MB 的 JSON 文本。除直注外，图片一律只在工具调用时按真实路径
使用（视觉顾问模式），不进入历史。直注时把图片复制到
<会话目录>/attachment/（按 1.png、2.jpg… 递增命名），历史只保留文本占位和
副本绝对路径；真正发给模型时再按路径读取编码。
"""

import base64
import json
import mimetypes
import os
import re

from src.utils.config import SESSIONS_DIR

ATTACHMENT_DIRNAME = "attachment"
DEFAULT_MAX_REQUEST_BYTES = 20 * 1024 * 1024
_ENV_MAX_REQUEST_BYTES = "PURRCAT_MAX_REQUEST_BYTES"

_SEQ_PATTERN = re.compile(r"^(\d+)\.(\w+)$")
_EXT_ALIASES = {".jpeg": ".jpg"}


def session_attachment_dir(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, session_id, ATTACHMENT_DIRNAME)


def max_request_bytes(model_cfg: dict | None = None) -> int:
    """单次请求体积上限（字节）：模型配置 > 环境变量 > 默认 20MB"""
    if isinstance(model_cfg, dict):
        value = model_cfg.get("max_request_bytes")
        if isinstance(value, int) and value > 0:
            return value
    try:
        value = int(os.getenv(_ENV_MAX_REQUEST_BYTES, ""))
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    return DEFAULT_MAX_REQUEST_BYTES


def _next_index(directory: str) -> int:
    max_index = 0
    try:
        for name in os.listdir(directory):
            matched = _SEQ_PATTERN.match(name)
            if matched:
                max_index = max(max_index, int(matched.group(1)))
    except FileNotFoundError:
        pass
    return max_index + 1


def _normalize_ext(ext: str) -> str:
    ext = (ext or ".png").lower()
    if not ext.startswith("."):
        ext = "." + ext
    return _EXT_ALIASES.get(ext, ext)


def store_image(session_id: str, raw: bytes, ext: str) -> str:
    """把图片字节写入会话 attachment/，返回副本绝对路径"""
    directory = session_attachment_dir(session_id)
    os.makedirs(directory, exist_ok=True)
    ext = _normalize_ext(ext)
    index = _next_index(directory)
    while True:
        path = os.path.join(directory, f"{index}{ext}")
        if not os.path.exists(path):
            break
        index += 1
    with open(path, "wb") as f:
        f.write(raw)
    return path


def _split_data_url(url: str):
    """data:image/png;base64,xxx → (mime, 图片字节)；非 data URL 返回 None"""
    if not url.startswith("data:") or ";base64," not in url:
        return None
    header, payload = url.split(";base64,", 1)
    mime = header[5:].split(";", 1)[0] or "image/png"
    try:
        return mime, base64.b64decode(payload)
    except Exception:
        return None


def _text_part(text: str, image_ref: str | None = None) -> dict:
    part = {"type": "text", "text": text}
    if image_ref:
        # image_ref 仅存在于历史，发送模型前会被还原为 image_url，不会外泄给 API
        part["image_ref"] = image_ref
    return part


def snapshot_message(message: dict, session_id: str) -> dict:
    """旧会话迁移：加载历史时把存量 base64 图片转成会话副本 + 路径占位"""
    if not session_id:
        return message
    content = message.get("content")
    if not isinstance(content, list):
        return message

    parts = []
    changed = False
    for part in content:
        if not isinstance(part, dict) or part.get("type") != "image_url":
            parts.append(part)
            continue
        url = (part.get("image_url") or {}).get("url", "")
        decoded = _split_data_url(url)
        if not decoded:
            parts.append(part)
            continue
        mime, raw = decoded
        ext = mimetypes.guess_extension(mime) or ".png"
        try:
            path = store_image(session_id, raw, ext)
        except Exception as e:
            print(f"[Warn.Attachment] 图片副本落盘失败，保留原 base64: {e}")
            parts.append(part)
            continue
        parts.append(_text_part(f"[图片 {os.path.basename(path)}]", path))
        changed = True

    if not changed:
        return message
    new_message = dict(message)
    new_message["content"] = parts
    return new_message


def materialize_message(message: dict) -> dict:
    """发送模型前：路径占位 → 真实 base64；副本丢失则降级为文本"""
    content = message.get("content")
    if not isinstance(content, list):
        return message

    parts = []
    changed = False
    for part in content:
        ref = part.get("image_ref") if isinstance(part, dict) else None
        if not ref:
            parts.append(part)
            continue
        name = os.path.basename(ref)
        try:
            with open(ref, "rb") as f:
                raw = f.read()
        except Exception:
            parts.append(_text_part(f"[图片已丢失: {name}]"))
            changed = True
            continue
        ext = os.path.splitext(ref)[1].lower()
        mime = mimetypes.guess_type(f"file{ext}")[0] or "image/png"
        data_url = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
        parts.append({"type": "image_url", "image_url": {"url": data_url}})
        changed = True

    if not changed:
        return message
    new_message = dict(message)
    new_message["content"] = parts
    return new_message


def serialized_size(messages: list) -> int:
    return len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))


def build_ref_part(session_id: str, raw: bytes, ext: str) -> dict:
    """把图片字节存入会话 attachment/，返回历史用的文本占位 part"""
    path = store_image(session_id, raw, ext)
    return _text_part(f"[图片 {os.path.basename(path)}]", path)

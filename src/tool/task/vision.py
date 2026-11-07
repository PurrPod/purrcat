"""视觉顾问功能 - 将宿主机图片/视频/音频附件转码并交由大模型分析"""

import base64
import mimetypes
from openai import OpenAI

from src.tool.filesystem.exceptions import ImageReadError
from src.tool.filesystem.utils import require_read
from src.utils.config import get_model_config

VISION_SYSTEM_PROMPT = """你是视觉顾问，按附件场景给出专业分析：

【网页/前端/设计稿分析】：
- 检查溢出、错位、重叠、遮挡
- 评估字体搭配与字号层级
- 评估配色协调性与文字对比度
- 检查对齐、留白、视觉层次

【音视频分析】：描述关键画面/音频内容，尽量标注时间点。

要求：回答具体、指向明确（给坐标或具体位置），避免空泛评价，回答用户 prompt 关心的问题。"""


def _media_kind(path: str) -> str:
    """返回媒体类别: 'image' / 'video' / 'audio'，无法识别返回 ''。"""
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        return ""
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    return ""


def _encode_media(file_path: str) -> dict:
    """读取单个媒体文件（图片/视频/音频）并转为 OpenAI/Qwen 多模态格式的 base64 字典。

    按 MIME 主类型分发到对应字段：
      - image/* -> image_url
      - video/* -> video_url
      - audio/* -> audio_url
    """
    kind = _media_kind(file_path)
    if not kind:
        raise ImageReadError(f"无法识别或不支持的文件类型: {file_path}")

    mime_type, _ = mimetypes.guess_type(file_path)
    with open(file_path, "rb") as f:
        base64_str = base64.b64encode(f.read()).decode("utf-8")

    data_url = f"data:{mime_type};base64,{base64_str}"
    key = f"{kind}_url"  # image_url / video_url / audio_url
    return {"type": key, key: {"url": data_url}}


def _get_vision_config():
    """从配置文件获取 vision 配置"""
    model_config = get_model_config()
    vision_config = model_config.get("vision", {})

    if not vision_config:
        raise ImageReadError("未配置 vision 模型，请在 model.json 中配置 vision 项")

    model_name, model_info = next(iter(vision_config.items()))

    api_keys = model_info.get("api_keys", [])
    if isinstance(api_keys, str):
        api_keys = [api_keys]

    if not api_keys:
        raise ImageReadError("vision 配置中缺少 api_keys")

    base_url = model_info.get("base_url")
    if not base_url:
        raise ImageReadError("vision 配置中缺少 base_url")

    return {
        "model_name": model_name,
        "api_key": api_keys[0],
        "base_url": base_url,
    }


def vision_inline(paths: list, session_id: str | None = None) -> dict:
    """🌟 vision 直注模式：直接读取图片附件构造 OpenAI 多模态 content 列表。

    调用方模型自身支持视觉（model.json 配置 vision=true）时，Task 的 vision
    action 不再走视觉顾问模型+prompt 分析，而是把图片本体直接塞回对话历史
    （相当于读取图片），prompt 参数无需填写。
    仅支持 API 实际接受的位图格式（png/jpg/jpeg/gif/webp）。

    session_id 非空时，图片会复制到该会话的 attachment/ 目录，历史里只写
    「[图片 1.png]」文本占位 + 副本路径，调用模型前再还原 base64，避免会话
    JSON 被 base64 撑爆；为空时（如子代理临时上下文）仍按原样内联。
    """
    import base64
    import os
    import time

    # OpenAI 兼容接口实际接受的图片格式（SVG/BMP 等会被 API 以 400 拒绝）
    _INLINE_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

    if isinstance(paths, str):
        paths = [paths]
    if not paths:
        raise ImageReadError("未提供任何有效的附件路径")

    resolved_paths = [require_read(p) for p in paths]

    # 校验：vision 直注仅支持 API 接受的位图格式（OpenAI content parts 规范）
    for p in resolved_paths:
        ext = os.path.splitext(p)[1].lower()
        if ext == ".svg":
            raise ImageReadError(
                f"SVG 是矢量文本格式，API 不支持直注（仅支持 png/jpg/jpeg/gif/webp）: {p}\n"
            )
        if ext not in _INLINE_IMAGE_EXTS:
            raise ImageReadError(
                f"vision 直注模式仅支持 png/jpg/jpeg/gif/webp 位图: {p}（{ext} 不受 API 支持）"
            )

    parts = [
        {
            "type": "text",
            "text": (f"[vision直注] 已直接读取 {len(resolved_paths)} 张图片"),
        }
    ]
    for path in resolved_paths:
        mime_type, _ = mimetypes.guess_type(path)
        with open(path, "rb") as f:
            raw = f.read()
        if session_id:
            # 副本落会话目录，历史只保留路径占位
            from src.utils.attachments import build_ref_part

            ext = os.path.splitext(path)[1] or ".png"
            parts.append(build_ref_part(session_id, raw, ext))
            continue
        b64 = base64.b64encode(raw).decode("utf-8")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64}"},
            }
        )

    return {
        "content": parts,
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": "text",
            "snip": f"查看了 {len(resolved_paths)} 张图片",
        },
    }


def _extract_message(message) -> tuple:
    """从响应消息中提取 (content, reasoning_content)，兼容 pydantic 与普通对象。"""
    raw = message.model_dump() if hasattr(message, "model_dump") else vars(message)
    return raw.get("content") or "", raw.get("reasoning_content") or ""


def vision(paths: list, prompt: str) -> dict:
    """
    读取一个或多个图片/视频/音频附件，转码为 base64 并按 OpenAI 多模态格式发送给视觉大模型。

    Args:
        paths: 单个附件路径字符串，或附件路径字符串列表（支持图片/视频/音频）
        prompt: 提示词
    """
    if isinstance(paths, str):
        paths = [paths]

    if not paths:
        raise ImageReadError("未提供任何有效的附件路径")

    # 批量校验权限
    resolved_paths = [require_read(p) for p in paths]

    # 校验媒体类型：只接受图片/视频/音频
    kinds = {p: _media_kind(p) for p in resolved_paths}
    unsupported = [p for p, k in kinds.items() if not k]
    if unsupported:
        raise ImageReadError(
            f"无法识别或不支持的附件类型: {unsupported}，仅支持图片/视频/音频"
        )

    vision_config = _get_vision_config()

    # 构建大模型的多模态 payload content
    content_list = [{"type": "text", "text": prompt}]
    for path in resolved_paths:
        content_list.append(_encode_media(path))

    messages = [
        {"role": "system", "content": VISION_SYSTEM_PROMPT},
        {"role": "user", "content": content_list},
    ]

    # 2. 调用 OpenAI 兼容接口
    try:
        client = OpenAI(
            api_key=vision_config["api_key"],
            base_url=vision_config["base_url"],
            timeout=120,
        )

        actual_model = (
            vision_config["model_name"].split(":", 1)[1]
            if ":" in vision_config["model_name"]
            else vision_config["model_name"]
        )

        # 不设 max_tokens：思考型模型的思考与正文共享输出预算，人为设小会把预算
        # 全耗在思考上导致正文为空；输出上限交给服务端按模型能力自行控制
        response = client.chat.completions.create(
            model=actual_model,
            messages=messages,
            extra_body={"enable_thinking": False},
        )
        choice = response.choices[0]
        result_text, reasoning_text = _extract_message(choice.message)

    except Exception as e:
        raise ImageReadError(f"视觉模型调用失败: {e}")

    # 正文为空：多半是模型输出超限（思考耗尽预算，finish_reason=length），直接报错给 agent
    if not result_text.strip():
        raise ImageReadError(
            f"vision 模型 {actual_model} 返回空正文 "
            f"(finish_reason={choice.finish_reason}, 思考内容 {len(reasoning_text)} 字)，"
            f"模型输出疑似超限"
        )

    return {
        "attachment_count": len(resolved_paths),
        "paths": resolved_paths,
        "analysis_result": result_text,
        "message": f"成功分析了 {len(resolved_paths)} 个附件",
    }

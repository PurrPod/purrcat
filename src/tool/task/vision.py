"""视觉顾问功能 - 将宿主机图片/视频/音频附件转码并交由大模型分析 (图片失败时 OCR 兜底)"""

import base64
import mimetypes
from openai import OpenAI

from src.tool.filesystem.exceptions import ImageReadError
from src.tool.filesystem.utils import require_read
from src.utils.config import get_model_config


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


def _fallback_ocr(paths: list, original_error: str) -> dict:
    """OCR 兜底识别函数（仅适用于图片附件）"""
    try:
        import easyocr

        # 默认加载简中和英文识别模型，禁用 GPU 以提升兼容性
        reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
    except ImportError:
        # 如果连 easyocr 都没有，则抛出带有详细提示的终极异常
        raise ImageReadError(
            f"视觉大模型不可用 ({original_error})，且环境未安装 easyocr 无法进行 OCR 兜底。\n"
            f"💡 提示：请在终端运行 `pip install easyocr` 以启用兜底功能。"
        )

    results = []
    for path in paths:
        try:
            # easyocr 直接支持传入本地路径读取
            ocr_results = reader.readtext(path)
            # 过滤掉置信度低于 0.4 的结果
            text = " ".join([item[1] for item in ocr_results if item[2] > 0.4])
            if not text.strip():
                text = "[未识别到明显文字]"
            results.append(f"【文件】{path} 的 OCR 识别结果:\n{text}")
        except Exception as e:
            results.append(f"【文件】{path} 的 OCR 识别失败: {str(e)}")

    return {
        "image_count": len(paths),
        "paths": paths,
        "analysis_result": f"⚠️ [系统提示: 视觉大模型不可用，已自动兜底使用 OCR 提取文本]\n失败原因: {original_error}\n\n"
        + "\n\n".join(results),
        "message": f"视觉大模型调用失败，使用 OCR 兜底读取了 {len(paths)} 张图片",
    }


def vision(paths: list, prompt: str) -> dict:
    """
    读取一个或多个图片/视频/音频附件，转码为 base64 并按 OpenAI 多模态格式发送给视觉大模型。
    仅当附件全部为图片且大模型不可用时，才使用 OCR 兜底。

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

    # 校验媒体类型并分类：只有图片能走 OCR 兜底，音视频不行
    kinds = {p: _media_kind(p) for p in resolved_paths}
    unsupported = [p for p, k in kinds.items() if not k]
    if unsupported:
        raise ImageReadError(
            f"无法识别或不支持的附件类型: {unsupported}，仅支持图片/视频/音频"
        )
    image_paths = [p for p in resolved_paths if kinds[p] == "image"]
    non_image_paths = [p for p in resolved_paths if kinds[p] != "image"]

    # 1. 尝试获取 vision 配置 (若未配置：仅纯图片场景可走 OCR 兜底)
    try:
        vision_config = _get_vision_config()
    except ImageReadError as e:
        if non_image_paths:
            raise ImageReadError(
                f"视觉大模型不可用 ({e})，且附件中含音视频无法用 OCR 兜底，请配置可用的 vision 模型"
            )
        return _fallback_ocr(image_paths, str(e))

    # 构建大模型的多模态 payload content
    content_list = [{"type": "text", "text": prompt}]
    for path in resolved_paths:
        content_list.append(_encode_media(path))

    messages = [{"role": "user", "content": content_list}]

    # 2. 尝试调用 OpenAI 兼容接口 (网络报错/超时：仅纯图片场景可走 OCR 兜底)
    try:
        client = OpenAI(
            api_key=vision_config["api_key"], base_url=vision_config["base_url"]
        )

        actual_model = (
            vision_config["model_name"].split(":", 1)[1]
            if ":" in vision_config["model_name"]
            else vision_config["model_name"]
        )

        response = client.chat.completions.create(
            model=actual_model,
            messages=messages,
            max_tokens=2000,
        )

        result_text = response.choices[0].message.content

        return {
            "attachment_count": len(resolved_paths),
            "paths": resolved_paths,
            "analysis_result": result_text,
            "message": f"成功分析了 {len(resolved_paths)} 个附件",
        }

    except Exception as e:
        # API 异常时：含音视频则直接报错，纯图片则触发 OCR 兜底
        if non_image_paths:
            raise ImageReadError(
                f"API 访问异常: {str(e)}，且附件中含音视频无法用 OCR 兜底"
            )
        return _fallback_ocr(image_paths, f"API 访问异常: {str(e)}")

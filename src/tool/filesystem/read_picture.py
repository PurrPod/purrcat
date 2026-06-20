"""图片读取功能 - 将宿主机图片转码并交由大模型分析 (增加 OCR 兜底)"""

import base64
import mimetypes
from openai import OpenAI

from src.tool.filesystem.exceptions import ImageReadError
from src.tool.filesystem.utils import require_read
from src.utils.config import get_model_config


def _encode_image(image_path: str) -> dict:
    """读取单张图片并转换为带 MIME 类型的 base64 字典"""
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/jpeg"

    with open(image_path, "rb") as image_file:
        base64_str = base64.b64encode(image_file.read()).decode("utf-8")

    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime_type};base64,{base64_str}"},
    }


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
    """OCR 兜底识别函数"""
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
        "analysis_result": f"⚠️ [系统提示: 视觉大模型不可用，已自动兜底使用 OCR 提取文本]\n失败原因: {original_error}\n\n" + "\n\n".join(results),
        "message": f"视觉大模型调用失败，使用 OCR 兜底读取了 {len(paths)} 张图片",
    }


def read_picture(paths: list, prompt: str) -> dict:
    """
    读取单张或多张图片，转码为 Base64 并发送给大模型，失败时使用 OCR 兜底。

    Args:
        paths: 单个图片路径字符串，或图片路径字符串列表
        prompt: 提示词
    """
    if isinstance(paths, str):
        paths = [paths]

    if not paths:
        raise ImageReadError("未提供任何有效的图片路径")

    # 批量校验权限
    resolved_paths = [require_read(p) for p in paths]

    # 1. 尝试获取 vision 配置 (如果未配置，直接进入 OCR 兜底)
    try:
        vision_config = _get_vision_config()
    except ImageReadError as e:
        return _fallback_ocr(resolved_paths, str(e))

    # 构建大模型的 payload content
    content_list = [{"type": "text", "text": prompt}]

    for path in resolved_paths:
        image_obj = _encode_image(path)
        content_list.append(image_obj)

    messages = [{"role": "user", "content": content_list}]

    # 2. 尝试调用 OpenAI Vision API (网络报错/超时也进入 OCR 兜底)
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
            "image_count": len(resolved_paths),
            "paths": resolved_paths,
            "analysis_result": result_text,
            "message": f"成功分析了 {len(resolved_paths)} 张图片",
        }

    except Exception as e:
        # API 异常时触发兜底
        return _fallback_ocr(resolved_paths, f"API 访问异常: {str(e)}")
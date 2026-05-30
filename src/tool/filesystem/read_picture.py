"""图片读取功能 - 将宿主机图片转码并交由大模型分析"""

import os
import base64
import mimetypes
from openai import OpenAI

from src.tool.filesystem.exceptions import (
    HostPathNotFoundError,
    PermissionDeniedError,
    ImageReadError
)
from src.utils.config import get_model_config

def _load_blacklist():
    """复用现有的黑名单机制"""
    from src.utils.config import get_file_config
    raw_list = get_file_config().get("dont_read_dirs", [])
    return [os.path.normcase(os.path.abspath(d)) for d in raw_list]

def _check_allowed(path: str, blacklist: list) -> bool:
    path_norm = os.path.normcase(os.path.abspath(path))
    for rule_norm in blacklist:
        try:
            if os.path.commonpath([path_norm, rule_norm]) == rule_norm:
                return False
        except ValueError:
            pass
    return True

def _encode_image(image_path: str) -> dict:
    """读取单张图片并转换为带 MIME 类型的 base64 字典"""
    if not os.path.exists(image_path):
        raise HostPathNotFoundError(image_path)
    
    # 检查黑名单
    if not _check_allowed(image_path, _load_blacklist()):
        raise PermissionDeniedError(image_path, "路径在黑名单中，不可读取图片")

    # 推断图片 MIME 类型，默认使用 jpeg
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/jpeg"

    with open(image_path, "rb") as image_file:
        base64_str = base64.b64encode(image_file.read()).decode('utf-8')
        
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:{mime_type};base64,{base64_str}"
        }
    }

def _get_vision_config():
    """从配置文件获取 vision 配置"""
    model_config = get_model_config()
    vision_config = model_config.get("vision", {})
    
    if not vision_config:
        raise ImageReadError("未配置 vision 模型，请在 model.json 中配置 vision 项")
    
    # 获取第一个 vision 配置
    model_name, model_info = next(iter(vision_config.items()))
    
    # 处理 api_keys，可能是字符串或列表
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
        "api_key": api_keys[0],  # 使用第一个 API key
        "base_url": base_url
    }

def read_picture(paths, prompt: str) -> dict:
    """
    读取单张或多张图片，转码为 Base64 并发送给大模型
    
    Args:
        paths: 单个图片路径字符串，或图片路径字符串列表
        prompt: 提示词
    """
    if isinstance(paths, str):
        paths = [paths]

    if not paths:
        raise ImageReadError("未提供任何有效的图片路径")

    # 获取 vision 配置
    vision_config = _get_vision_config()
    
    # 构建大模型的 payload content
    content_list = [{"type": "text", "text": prompt}]
    
    for path in paths:
        image_obj = _encode_image(path)
        content_list.append(image_obj)

    messages = [
        {
            "role": "user",
            "content": content_list
        }
    ]

    try:
        # 从配置初始化 OpenAI client
        client = OpenAI(
            api_key=vision_config["api_key"],
            base_url=vision_config["base_url"]
        )
        
        # 从 model_name 中提取实际的模型名称，格式为 "openai:model-name"
        actual_model = vision_config["model_name"].split(":", 1)[1] if ":" in vision_config["model_name"] else vision_config["model_name"]
        
        response = client.chat.completions.create(
            model=actual_model,
            messages=messages,
            max_tokens=2000,
        )
        
        result_text = response.choices[0].message.content
        
        return {
            "image_count": len(paths),
            "paths": paths,
            "analysis_result": result_text,
            "message": f"成功分析了 {len(paths)} 张图片"
        }
        
    except Exception as e:
        raise ImageReadError(f"调用视觉大模型时发生异常: {str(e)}")

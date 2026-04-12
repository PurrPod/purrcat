import json
import os
import uuid
import base64
import urllib.request
from typing import List, Union

from openai import OpenAI
from src.utils.config import get_specialized_model, BUFFER_DIR


def _get_client(model_type: str):
    """从 config.yaml 中读取对应模型配置，并构造 OpenAI 客户端。"""
    info = get_specialized_model(model_type)
    
    if not info:
        raise KeyError(f"配置文件中未找到 '{model_type}' 部分")

    name = info.get("name") or ""
    api_key = info.get("api_key") or ""
    base_url = info.get("base_url") or ""

    if not name or not api_key or not base_url:
        raise ValueError(
            f"请在 config.yaml 中补充 '{model_type}' 的 name/api_key/base_url 信息。"
        )

    client = OpenAI(api_key=api_key, base_url=base_url)
    return name, client


def _ensure_list(ref_path: Union[str, List[str], None]) -> List[str]:
    """辅助函数：将传入的 ref_path 统一处理为 List[str]"""
    if not ref_path:
        return []
    if isinstance(ref_path, str):
        return [ref_path]
    return ref_path


def _encode_image_to_base64(image_path: str) -> str:
    """辅助函数：将本地图片转换为 base64 编码"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def generate_image(prompt: str, output_dir: str = None) -> str:
    name, client = _get_client("image_generator")
    response = client.images.generate(
        model=name,
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    image_url = response.data[0].url
    output_dir = output_dir or ".buffer"
    os.makedirs(output_dir, exist_ok=True)
    file_name = f"generated_img_{uuid.uuid4().hex[:8]}.png"
    save_path = os.path.join(output_dir, file_name)
    urllib.request.urlretrieve(image_url, save_path)
    return save_path


def image_to_text(prompt: str, ref_path: Union[str, List[str]]) -> str:
    """使用 GPT-4o 进行视觉识别，支持单张或多张图片分析。"""
    ref_paths = _ensure_list(ref_path)
    messages_content = [{"type": "text", "text": prompt}]
    for path in ref_paths:
        base64_image = _encode_image_to_base64(path)
        messages_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}"
            }
        })
    name, client = _get_client("image_converter")
    response = client.chat.completions.create(
        model=name,
        messages=[{"role": "user","content": messages_content}]
    )
    return response.choices[0].message.content

def generate_video(prompt: str, ref_path: Union[str, List[str]] = None, output_dir: str = None) -> str:
    # 构造兼容 OpenAI 格式的底层请求
    name, client = _get_client("video_generator")
    response = client.post(
        "/videos/generations",
        cast_to=dict,
        body={
            "model": name,  # 根据你接入的代理平台替换具体模型名
            "prompt": prompt
        }
    )
    video_url = response.get("data", [{}])[0].get("url")
    if not video_url:
        raise ValueError("视频生成失败，未获取到视频URL")
    output_dir = output_dir or ".buffer"
    os.makedirs(output_dir, exist_ok=True)
    file_name = f"generated_video_{uuid.uuid4().hex[:8]}.mp4"
    save_path = os.path.join(output_dir, file_name)
    urllib.request.urlretrieve(video_url, save_path)
    return save_path


def video_to_text(prompt: str, ref_path: Union[str, List[str]]) -> str:
    ref_paths = _ensure_list(ref_path)
    if not ref_paths:
        return "未提供视频文件路径。"
    video_path = ref_paths[0]  # 这里以处理列表中第一个视频为例
    try:
        import cv2
    except ImportError:
        return "未安装 opencv-python，无法处理视频文件。请先 pip install opencv-python。"

    video = cv2.VideoCapture(video_path)
    base64_frames = []
    while video.isOpened():
        success, frame = video.read()
        if not success:
            break
        _, buffer = cv2.imencode(".jpg", frame)
        base64_frames.append(base64.b64encode(buffer).decode("utf-8"))
    video.release()
    total_frames = len(base64_frames)
    if total_frames == 0:
        return "无法读取视频帧。"
    sample_interval = max(1, total_frames // 10)
    sampled_frames = [base64_frames[i] for i in range(0, total_frames, sample_interval)][:10]
    messages_content = [{"type": "text", "text": prompt}]
    for frame_b64 in sampled_frames:
        messages_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{frame_b64}"
            }
        })
    name, client = _get_client("video_converter")
    response = client.chat.completions.create(
        model=name,
        messages=[
            {"role": "user", "content": messages_content}
        ]
    )
    return response.choices[0].message.content


def generate_audio(prompt: str, ref_path: Union[str, List[str]] = None, output_dir: str = None) -> str:
    output_dir = output_dir or "."
    os.makedirs(output_dir, exist_ok=True)
    file_name = f"generated_audio_{uuid.uuid4().hex[:8]}.mp3"
    save_path = os.path.join(output_dir, file_name)
    name, client = _get_client("audio_generator")
    with client.audio.speech.with_streaming_response.create(
            model=name,
            voice="alloy",  # 支持 alloy, echo, fable, onyx, nova, shimmer
            input=prompt
    ) as response:
        response.stream_to_file(save_path)
    return save_path

def audio_to_text(prompt: str, ref_path: Union[str, List[str]]) -> str:
    ref_paths = _ensure_list(ref_path)
    if not ref_paths:
        return "未提供音频文件路径。"
    audio_path = ref_paths[0]
    name, client = _get_client("audio_converter")
    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model=name,
            file=audio_file,
            prompt=prompt
        )
    return transcript.text


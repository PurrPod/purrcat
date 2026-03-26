import os
import sys
import time
import glob
import subprocess
import imageio_ffmpeg
import re
import json
from typing import Any

COOKIE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "cut-tool", "cookies.txt")
TEMP_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "bilibili", "temp")
OUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "bilibili")

_model = None


def _format_response(msg_type: str, content: Any) -> str:
    """统一返回JSON格式"""
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("base", device="cpu", compute_type="int8")
    return _model


def _detect_video_scenes(video_path: str) -> str:
    """使用 PySceneDetect 识别视频场景/关键帧"""
    try:
        # 延迟导入，避免未安装时直接崩溃
        from scenedetect import detect, ContentDetector
    except ImportError:
        return "⚠️ 未安装 scenedetect。请在终端运行: pip install scenedetect opencv-python"

    try:
        print("[bili_clipper] 开始场景/关键帧识别...")
        # ContentDetector 基于内容变化检测场景，适合大多数常规视频剪辑
        scene_list = detect(video_path, ContentDetector())

        if not scene_list:
            return "未能识别到明显的场景切换 (可能是一个长镜头)。"

        scenes_info = []
        for i, scene in enumerate(scene_list):
            # scene[0] 是开始时间，scene[1] 是结束时间 (包含高精度时间码)
            start_time = scene[0].get_timecode()
            end_time = scene[1].get_timecode()
            scenes_info.append(f"镜号 {i + 1:02d}: [{start_time} ~ {end_time}]")

        print("[bili_clipper] 场景识别完成")
        return "\n".join(scenes_info)
    except Exception as e:
        print(f"[bili_clipper] 场景识别异常: {str(e)}")
        return f"❌ 场景识别失败: {str(e)}"


def download_and_transcribe(url: str) -> str:
    """下载视频并返回时间戳字幕及场景时间戳，10分钟超时"""
    os.makedirs(TEMP_DIR, exist_ok=True)
    temp_base_name = f"temp_bili_{int(time.time())}"

    # 清理 URL - 去除空格、反引号、换行等
    clean_url = url.strip().strip('`').strip()
    clean_url = re.sub(r'\s+', '', clean_url)
    clean_url = clean_url.split('?')[0]

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    download_cmd = [
        sys.executable, '-m', 'yt_dlp',
        '--cookies', COOKIE_PATH,
        '--ffmpeg-location', ffmpeg_exe,
        '-f', 'bestvideo+bestaudio/best',
        '--merge-output-format', 'mp4',
        '-o', os.path.join(TEMP_DIR, f"{temp_base_name}.%(ext)s"),
        clean_url
    ]

    print(f"[bili_clipper] 开始下载: {clean_url}")
    print(f"[bili_clipper] Cookie路径: {COOKIE_PATH}")
    print(f"[bili_clipper] Cookie存在: {os.path.exists(COOKIE_PATH)}")

    # 10分钟超时
    TIMEOUT = 600

    try:
        result = subprocess.run(
            download_cmd,
            check=True,
            text=True,
            timeout=TIMEOUT
        )
        print("[bili_clipper] 下载命令执行完成")
    except subprocess.TimeoutExpired:
        print(f"[bili_clipper] 下载超时 ({TIMEOUT}s)")
        return _format_response("error", f"下载超时，已超过{TIMEOUT//60}分钟。请尝试更短的视频或检查网络连接。")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        print(f"[bili_clipper] 下载失败: {error_msg}")
        return _format_response("error", f"下载失败: {error_msg}\n\nURL: {clean_url}")
    except Exception as e:
        print(f"[bili_clipper] 异常: {str(e)}")
        return _format_response("error", f"下载异常: {str(e)}")

    search_pattern = os.path.join(TEMP_DIR, f"{temp_base_name}.*")
    found_files = glob.glob(search_pattern)
    if not found_files:
        return _format_response("error", f"下载成功但找不到视频文件\n\n搜索路径: {search_pattern}")

    video_path = found_files[0]
    print(f"[bili_clipper] 视频文件: {video_path}")

    try:
        print("[bili_clipper] 开始语音转文字...")
        model = _get_model()
        segments, info = model.transcribe(video_path, beam_size=5, language="zh")
        transcript = []
        for segment in segments:
            start_m, start_s = divmod(int(segment.start), 60)
            end_m, end_s = divmod(int(segment.end), 60)
            time_tag = f"[{start_m:02d}:{start_s:02d}~{end_m:02d}:{end_s:02d}]"
            transcript.append(f"{time_tag} {segment.text}")

        full_text = "\n".join(transcript)
        print("[bili_clipper] 转录完成")

        # 在此处调用场景识别功能
        scenes_text = _detect_video_scenes(video_path)

        result_content = {
            "video_path": video_path,
            "scenes": scenes_text,
            "transcript": full_text,
            "message": "下载与解析成功！"
        }
        return _format_response("success", result_content)

    except Exception as e:
        return _format_response("error", f"解析失败: {str(e)}\n\n视频路径: {video_path}")


def trim_video(video_path: str, start_time: str, end_time: str, output_name: str) -> str:
    """精准裁剪，10分钟超时"""
    os.makedirs(OUT_DIR, exist_ok=True)
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    _, ext = os.path.splitext(video_path)
    final_output = os.path.join(OUT_DIR, f"{output_name}{ext}")

    trim_cmd = [
        ffmpeg_exe, '-y',
        '-i', video_path,
        '-ss', start_time,
        '-to', end_time,
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-c:a', 'copy',
        final_output
    ]

    # 10分钟超时
    TIMEOUT = 600

    try:
        subprocess.run(trim_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT)
        return _format_response("success", f"裁剪成功！成片已保存至: {final_output}")
    except subprocess.TimeoutExpired:
        return _format_response("error", f"裁剪超时，已超过{TIMEOUT//60}分钟。")
    except subprocess.CalledProcessError as e:
        return _format_response("error", f"裁剪失败: {e.stderr.decode('utf-8', errors='ignore')}")

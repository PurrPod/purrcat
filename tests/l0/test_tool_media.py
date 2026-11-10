"""工具多媒体落盘与 vision 直注（SPEC-007）。"""

from __future__ import annotations

import base64
from pathlib import Path

from src.tool.utils.media import (
    build_vision_inline_parts,
    handle_media_content,
    image_data_url,
    is_openai_content_parts,
)


def test_is_openai_content_parts_requires_text_or_image_only():
    assert is_openai_content_parts([{"type": "text", "text": "hi"}])
    assert not is_openai_content_parts([])
    assert not is_openai_content_parts([{"type": "audio"}])
    assert not is_openai_content_parts({"type": "text"})


def test_image_data_url_infers_mime_and_keeps_explicit_mime():
    assert image_data_url("AAA", ".png") == "data:image/png;base64,AAA"
    assert (
        image_data_url("AAA", ".svg", "image/svg+xml")
        == "data:image/svg+xml;base64,AAA"
    )


def test_vision_parts_for_image_and_mcp_media():
    image_parts = build_vision_inline_parts(
        "image", {"data": "AAA", "ext": ".png"}, "shot"
    )
    mcp_parts = build_vision_inline_parts(
        "mcp_media", {"data": "BBB", "mimeType": "image/jpeg"}, "mcp"
    )

    assert image_parts[0]["type"] == "text"
    assert "/agent_vm/.buffer/vision_shot_" in image_parts[0]["text"]
    assert image_parts[1]["image_url"]["url"] == "data:image/png;base64,AAA"
    assert mcp_parts[1]["image_url"]["url"] == "data:image/jpeg;base64,BBB"


def test_vision_parts_reject_non_image_formats():
    assert build_vision_inline_parts("image", {"data": "A", "ext": ".svg"}, "t") is None
    assert (
        build_vision_inline_parts(
            "mcp_media", {"data": "A", "mimeType": "image/svg+xml"}, "t"
        )
        is None
    )
    assert build_vision_inline_parts("video", {"data": "A"}, "t") is None


def test_handle_media_content_passes_non_media_through(tmp_path):
    assert handle_media_content("plain", "echo", buffer_dir=str(tmp_path)) == "plain"
    payload = {"type": "text", "data": "x"}
    assert handle_media_content(payload, "echo", buffer_dir=str(tmp_path)) is payload


def test_handle_media_content_writes_image_and_returns_both_paths(tmp_path):
    encoded = base64.b64encode(b"png-bytes").decode()

    result = handle_media_content(
        {"type": "image", "data": encoded, "ext": ".png"},
        "shot",
        buffer_dir=str(tmp_path),
    )

    files = list((tmp_path).glob("shot_*.png"))
    assert len(files) == 1
    assert files[0].read_bytes() == b"png-bytes"
    assert "宿主机路径" in result
    assert "/agent_vm/.buffer/shot_" in result


def test_vision_mode_returns_parts_without_writing(tmp_path):
    result = handle_media_content(
        {"type": "image", "data": "AAA", "ext": ".png"},
        "shot",
        buffer_dir=str(tmp_path),
        vision_mode=True,
    )

    assert isinstance(result, list)
    assert list(Path(tmp_path).iterdir()) == []


def test_vision_mode_still_buffers_non_image_media(tmp_path):
    encoded = base64.b64encode(b"video-bytes").decode()

    result = handle_media_content(
        {"type": "video", "data": encoded, "ext": ".mp4"},
        "clip",
        buffer_dir=str(tmp_path),
        vision_mode=True,
    )

    assert isinstance(result, str)
    assert len(list(Path(tmp_path).glob("clip_*.mp4"))) == 1

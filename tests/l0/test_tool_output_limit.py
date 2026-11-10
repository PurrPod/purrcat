"""工具输出落盘与预览文案（SPEC-007）。"""

from __future__ import annotations

import json
from pathlib import Path

from src.tool.utils.output_limit import (
    overflow_prompt,
    safe_truncate,
    write_overflow_cache,
)


def test_write_overflow_cache_uses_tool_subdir_and_returns_filename(tmp_path):
    file_name = write_overflow_cache("完整内容", "bash", str(tmp_path))

    path = Path(tmp_path) / "bash" / file_name
    assert path.read_text(encoding="utf-8") == "完整内容"
    assert path.name.endswith(".txt")


def test_overflow_prompt_contains_path_count_and_preview():
    prompt = overflow_prompt(
        tool_name="bash",
        content_token_count=9000,
        max_output_tokens=1000,
        file_name="20260101_ab12.txt",
        preview="预览",
    )

    assert "bash 输出总长约 9000 token" in prompt
    assert "/agent_vm/.buffer/bash/20260101_ab12.txt" in prompt
    assert "前 1000 token" in prompt
    assert prompt.endswith("预览")


def test_safe_truncate_returns_full_json_when_within_budget():
    data = {"a": 1}

    assert json.loads(safe_truncate(data, 1000)) == data


def test_safe_truncate_marks_omitted_characters_when_over_budget():
    result = safe_truncate({"a": "字" * 2000}, 10)

    assert "字符已被截断" in result

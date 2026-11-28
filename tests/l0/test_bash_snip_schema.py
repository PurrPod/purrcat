"""Bash 工具 snip 参数契约（SPEC-046 / AC-1）。"""

from __future__ import annotations

from src.tool.bash.schema import BASH_TOOL_SCHEMA


def test_bash_schema_exposes_snip_for_frontend():
    params = BASH_TOOL_SCHEMA["function"]["parameters"]
    props = params["properties"]

    assert "snip" in props
    assert props["snip"]["type"] == "string"
    assert props["snip"]["description"].strip()
    # snip 只服务前端展示，保持可选以兼容旧调用
    assert params["required"] == ["command"]

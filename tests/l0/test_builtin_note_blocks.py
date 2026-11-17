"""Note 插件的块切分与行内编辑（L0，SPEC-032 AC-4）。"""

import json
import shutil
import subprocess
from pathlib import Path

HARNESS = Path(__file__).with_name("note_harness.cjs")


def _call(op: str, *args):
    node = shutil.which("node")
    assert node, "Note 插件测试需要 node"
    proc = subprocess.run(
        [node, str(HARNESS)],
        input=json.dumps({"op": op, "args": list(args)}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert not (isinstance(out, dict) and "error" in out and len(out) == 1), out[
        "error"
    ]
    return out


def test_split_blocks_kinds_and_ranges() -> None:
    """SPEC-032 AC-4：标题/列表/引用/表格/代码/段落各自成块且行范围准确。"""
    source = (
        "# 标题\n"
        "\n"
        "第一段\n"
        "第二行\n"
        "\n"
        "- 一\n"
        "- 二\n"
        "\n"
        "> 引用\n"
        "\n"
        "| a | b |\n"
        "| - | - |\n"
        "\n"
        "```js\n"
        "const a = 1;\n"
        "```\n"
        "\n"
        "```purrcat@none\n"
        "- TODO 写周报\n"
        "无描述\n"
        "```\n"
    )
    blocks = _call("splitBlocks", source)["blocks"]
    kinds = [b["kind"] for b in blocks]
    assert kinds == ["heading", "paragraph", "list", "quote", "table", "code", "card"]
    assert (blocks[0]["start"], blocks[0]["end"]) == (0, 1)
    assert (blocks[1]["start"], blocks[1]["end"]) == (2, 4)
    assert (blocks[2]["start"], blocks[2]["end"]) == (5, 7)
    assert (blocks[3]["start"], blocks[3]["end"]) == (8, 9)
    assert (blocks[4]["start"], blocks[4]["end"]) == (10, 12)
    assert (blocks[5]["start"], blocks[5]["end"]) == (13, 16)
    assert blocks[6]["kind"] == "card"
    assert blocks[6]["raw"].startswith("```purrcat@none")


def test_apply_block_edit_replaces_lines() -> None:
    """SPEC-032 AC-4：行内编辑按行范围替换，不碰其它块。"""
    source = "# 标题\n\n旧段落\n\n尾段\n"
    out = _call("applyBlockEdit", source, 2, 3, "新段落\n第二行")
    assert out == "# 标题\n\n新段落\n第二行\n\n尾段\n"


def test_split_blocks_handles_unfinished_fence() -> None:
    """SPEC-032 AC-4：未闭合围栏不会吞掉后续内容而报错。"""
    source = "```purrcat@none\n- TODO 未闭合\n"
    blocks = _call("splitBlocks", source)["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["kind"] == "card"
    assert blocks[0]["end"] == 3

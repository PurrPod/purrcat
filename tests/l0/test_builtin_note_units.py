"""Note 插件的行单元切分与点击落点映射（L0，SPEC-032 AC-4 / AC-6）。"""

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


def test_split_units_line_level_live_preview() -> None:
    """SPEC-032 AC-4：行级单元，空行与列表逐行可编辑，多行结构整体成单元。"""
    source = (
        "# 标题\n"
        "\n"
        "第一段\n"
        "第二行\n"
        "- 一\n"
        "- 二\n"
        "> 引用\n"
        "---\n"
        "| a | b |\n"
        "| - | - |\n"
        "```js\n"
        "const a = 1;\n"
        "```\n"
        "```purrcat@none\n"
        "- TODO 写周报\n"
        "无描述\n"
        "```\n"
    )
    units = _call("splitUnits", source)["units"]
    shape = [(u["kind"], u["start"], u["end"]) for u in units]
    assert shape == [
        ("heading", 0, 1),
        ("blank", 1, 2),
        ("paragraph", 2, 3),
        ("paragraph", 3, 4),
        ("list", 4, 5),
        ("list", 5, 6),
        ("quote", 6, 7),
        ("rule", 7, 8),
        ("table", 8, 10),
        ("code", 10, 13),
        ("card", 13, 17),
        ("blank", 17, 18),
    ]
    assert units[-2]["raw"].startswith("```purrcat@none")


def test_split_units_empty_source_keeps_one_line() -> None:
    """SPEC-032 AC-4：空文档保留一个可点击的空行落点。"""
    split = _call("splitUnits", "")
    assert split["lines"] == [""]
    assert split["units"] == [{"start": 0, "end": 1, "kind": "blank", "raw": ""}]


def test_map_rendered_offset_to_source() -> None:
    """SPEC-032 AC-6：点击渲染文本的位置能映射回原始源码偏移。"""
    assert _call("mapRenderedOffset", "## 标题", "标题", 0) == 3
    assert _call("mapRenderedOffset", "## 标题", "标题", 2) == 5
    assert _call("mapRenderedOffset", "- 写周报", "写周报", 0) == 2
    assert _call("mapRenderedOffset", "- 写周报", "写周报", 2) == 4
    assert _call("mapRenderedOffset", "**加粗** 文字", "加粗 文字", 2) == 4
    assert _call("mapRenderedOffset", "普通文字", "普通文字", 0) == 0
    assert _call("mapRenderedOffset", "普通文字", "普通文字", 4) == 4


def test_unit_at_finds_whole_multi_line_unit() -> None:
    """SPEC-032 AC-4：卡片内部任意一行都归属整个卡片单元，不能单行编辑围栏。"""
    source = "```purrcat@none\n- TODO 写周报\n无描述\n```\n"
    units = _call("splitUnits", source)["units"]
    assert _call("unitAt", units, 0)["kind"] == "card"
    assert _call("unitAt", units, 2)["kind"] == "card"
    assert _call("unitAt", units, 99) is None


def test_split_line_keeps_caret_on_new_line() -> None:
    """SPEC-032 AC-4：回车一次就在光标处分成两行，光标落到新行行首。"""
    assert _call("splitLine", ["abc"], 0, 1, 1) == {
        "lines": ["a", "bc"],
        "start": 1,
        "count": 1,
    }
    assert _call("splitLine", ["abc"], 0, 3, 3) == {
        "lines": ["abc", ""],
        "start": 1,
        "count": 1,
    }
    assert _call("splitLine", ["abcdef"], 0, 2, 4) == {
        "lines": ["ab", "ef"],
        "start": 1,
        "count": 1,
    }

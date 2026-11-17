"""Note 插件纯逻辑（L0，SPEC-032）。

通过 node harness 加载 builtin-note/core.js，验证时间窗、卡片格式与目标改写。
"""

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).with_name("note_harness.cjs")
NOTE_DIR = ROOT / "ui" / "web-minimal" / "plugins" / "builtin" / "builtin-note"


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


def test_plugin_entry_and_core_exist() -> None:
    """SPEC-032 AC-5：插件入口、清单、纯逻辑与共享依赖齐备。"""
    for name in ("plugin.json", "index.html", "core.js"):
        assert (NOTE_DIR / name).is_file(), name
    manifest = json.loads((NOTE_DIR / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "builtin-note"
    assert manifest["slot"] == {"area": "panel"}
    assert manifest["entry"] == "index.html"
    assert {"name": "marked", "range": "^12"} in manifest["requires"]


def test_time_window_and_progress() -> None:
    """SPEC-032 AC-1：普通与跨午夜时间窗的进度。"""
    win = _call("dayWindow", "08:00", "23:00")
    assert win["wake"] == 480 and win["sleep"] == 1380 and win["span"] == 900

    night = _call("dayWindow", "22:00", "06:00")
    assert night["crossing"] is True and night["span"] == 480

    assert _call("dayProgress", 420, "08:00", "23:00") == {
        "percent": 0,
        "phase": "before",
    }
    assert _call("dayProgress", 900, "08:00", "23:00")["percent"] == 46.67
    assert _call("dayProgress", 1400, "08:00", "23:00") == {
        "percent": 100,
        "phase": "after",
    }

    assert _call("dayProgress", 1320, "22:00", "06:00") == {
        "percent": 0,
        "phase": "awake",
    }
    assert _call("dayProgress", 60, "22:00", "06:00")["percent"] == 37.5
    assert _call("dayProgress", 420, "22:00", "06:00") == {
        "percent": 0,
        "phase": "before",
    }


def test_ratio_time_conversion() -> None:
    """SPEC-032 AC-2：拖拽比例与时间点互转。"""
    assert _call("ratioToMinutes", 0, "08:00", "23:00") == 480
    assert _call("ratioToMinutes", 0.5, "08:00", "23:00") == 930
    assert _call("ratioToMinutes", 1, "22:00", "06:00") == 360
    assert _call("minutesToRatio", 930, "08:00", "23:00") == 50
    assert _call("minutesToRatio", 60, "22:00", "06:00") == 37.5


def test_build_and_append_purr_block() -> None:
    """SPEC-032 AC-2：块格式严格匹配，追加处保留空行分隔。"""
    block = _call("buildPurrBlock", {"title": "写周报"})
    assert block == "```purrcat@none\n- TODO 写周报\n# 写周报\n无描述\n```"
    timed = _call("buildPurrBlock", {"title": "喝水", "start": 540, "end": 600})
    assert timed == "```purrcat@none\n- TODO 09:00~10:00 60min\n# 喝水\n无描述\n```"
    midnight = _call("buildPurrBlock", {"title": "收尾", "start": 1410, "end": 1440})
    assert "- TODO 23:30~24:00 30min" in midnight
    main_block = _call(
        "buildPurrBlock",
        {"title": "整理 inbox", "target": "main", "session": "session_abc"},
    )
    assert main_block.splitlines()[0] == "```purrcat@main/session_abc"

    assert _call("appendBlock", "", block) == block + "\n"
    assert _call("appendBlock", "# 标题\n", block) == "# 标题\n\n" + block + "\n"


def test_parse_cards_and_update_only_fence() -> None:
    """SPEC-032 AC-3：解析时间段/时长/target/session，改写目标只替换围栏首行。"""
    source = (
        "# 今天\n\n```purrcat@main/session_abc\n"
        "- TODO 14:00~15:30 90min\n# 写周报\n下午完成\n```\n"
    )
    cards = _call("parseCards", source)
    assert len(cards) == 1
    card = cards[0]
    assert card["target"] == "main"
    assert card["session"] == "session_abc"
    assert card["title"] == "写周报"
    assert card["time"] == "14:00~15:30"
    assert card["duration"] == "90min"
    assert card["description"] == "下午完成"
    assert card["start"] == 2 and card["end"] == 7

    updated = _call("updateCardRef", source, card, "daily", "")
    assert "```purrcat@daily\n" in updated
    assert "- TODO 14:00~15:30 90min\n# 写周报\n下午完成" in updated
    assert "purrcat@main" not in updated

    none_card = _call("parseCards", _call("buildPurrBlock", {"title": "x"}))[0]
    assert none_card["target"] == "none"
    assert none_card["time"] == ""
    assert none_card["duration"] == ""
    assert none_card["description"] == "无描述"


def test_parse_card_keeps_legacy_todo_title() -> None:
    """SPEC-032 AC-3：旧格式把标题写在 TODO 行时仍能解析，时长按时间段推算。"""
    card = _call(
        "parseCards",
        "```purrcat@none\n- TODO 09:00~10:00 写周报\n# 写周报\n无描述\n```",
    )[0]
    assert card["title"] == "写周报"
    assert card["time"] == "09:00~10:00"
    assert card["duration"] == "60min"

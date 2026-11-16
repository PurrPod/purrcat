"""GenUI DSL 解析与渲染（L0）。

通过 node harness 加载前端 GenUI 运行时，验证 DSL 解析、求值与 HTML 输出。
"""

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).with_name("genui_harness.cjs")
GENUI_DIR = (
    ROOT / "ui" / "web-minimal" / "plugins" / "builtin" / "builtin-history" / "genui"
)


def _render(source: str, state: dict | None = None) -> str:
    payload = _run({"source": source, "state": state or {}})
    assert "error" not in payload, payload.get("error")
    return payload["html"]


def _run(payload: dict) -> dict:
    node = shutil.which("node")
    assert node, "GenUI DSL 测试需要 node"
    proc = subprocess.run(
        [node, str(HARNESS)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_genui_runtime_files_exist() -> None:
    for name in (
        "core.js",
        "functions.js",
        "render.js",
        "media.js",
        "components-common.js",
        "components-text.js",
        "components-input.js",
        "components-data.js",
        "components-chart.js",
        "components-draw.js",
        "index.js",
        "genui.css",
    ):
        assert (GENUI_DIR / name).is_file(), name


def test_layout_and_inline_markup() -> None:
    html = _render('root = Col([Title("Hello"), Text("**bold** and `code`")], 3)')
    assert 'class="gui-col"' in html
    assert "gap:12px" in html
    assert "Hello" in html
    assert "<strong>bold</strong>" in html
    assert "gui-inline-code" in html


def test_state_variables_and_expressions() -> None:
    html = _render(
        '$name = "Ada"\n$count = 2\n'
        'root = Text("Hi " + $name + " x" + ($count * 3) + ($count > 1 ? "!" : "?"))'
    )
    assert "Hi Ada x6!" in html


def test_each_filter_sort_and_nested_item() -> None:
    source = (
        '$rows = [{name: "A", v: 12}, {name: "B", v: 30}, {name: "C", v: 7}]\n'
        'root = List(@Each(@Sort(@Filter($rows, "v", ">", 10), "v", "desc"), "r", ListItem(r.name, "v=" + r.v)))'
    )
    html = _render(source)
    assert "B" in html and "A" in html
    assert "C" not in html
    assert html.index("B") < html.index("A")
    assert "v=30" in html


def test_table_numbers_align_right() -> None:
    html = _render('root = Table(["Name", "Value"], [["A", 12], ["B", 30]])')
    assert 'class="gui-table"' in html
    assert "<th>Name</th>" in html
    assert '<td class="num">12</td>' in html


def test_chart_renders_svg_series() -> None:
    html = _render(
        '$data = [{m: "Jan", a: 3, b: 5}, {m: "Feb", a: 6, b: 2}]\n'
        'root = Chart("bar", $data, "m", ["a", "b"], "compact", null, true, 200)'
    )
    assert "gui-chart-svg" in html
    assert 'viewBox="0 0 640 200"' in html
    assert "var(--gui-chart-1)" in html
    assert "Jan" in html


def test_pie_chart_and_legend() -> None:
    html = _render(
        'root = Chart("donut", [{k: "A", v: 1}, {k: "B", v: 3}], "k", ["v"])'
    )
    assert "gui-chart-total" in html
    assert "A: 1" in html


def test_map_projection_route_and_labels() -> None:
    html = _render(
        'root = Map([{label: "Paris", lat: 48.85, lng: 2.35}, {label: "Lyon", lat: 45.76, lng: 4.83}], true)'
    )
    assert "gui-map" in html
    assert "<polyline" in html
    assert "Paris" in html and "Lyon" in html
    assert "2 个地点" in html


def test_form_controls_bind_state() -> None:
    html = _render(
        '$name = "Ada"\n$plan = "pro"\n'
        'root = Form([Input($name, "Name"), Select($plan, [{value: "free", label: "Free"}, '
        '{value: "pro", label: "Pro"}], "Plan"), Checkbox($name, "Agree")])'
    )
    assert 'data-bind="name"' in html
    assert 'value="Ada"' in html
    assert '<option value="pro" selected>Pro</option>' in html
    assert 'type="checkbox"' in html


def test_svg_drawing_components() -> None:
    html = _render(
        'root = Svg([Circle(20, 20, 10, "chart1"), Rect(40, 10, 20, 20, 4, "chart2"), '
        'Line(0, 0, 100, 100, "ink", 3), SvgText("Hi", 10, 60, 12, "ink", "middle")], 120, 80)'
    )
    assert "gui-svg" in html
    assert '<circle cx="20" cy="20" r="10"' in html
    assert '<rect x="40" y="10" width="20" height="20"' in html
    assert 'rx="4"' in html
    assert ">Hi</text>" in html


def test_flashcard_and_html_view() -> None:
    html = _render(
        'root = Col([Flashcard("front", "back", "hint"), HtmlView("<b>ok</b>", 200, "demo")])'
    )
    assert "gui-flashcard" in html
    assert "正面" in html and "背面" in html
    assert 'sandbox="allow-scripts allow-forms"' in html
    assert "&lt;b&gt;ok&lt;/b&gt;" in html


def test_builtin_functions() -> None:
    html = _render(
        '$rows = [{team: "A", score: 1}, {team: "A", score: 3}, {team: "B", score: 2}]\n'
        'root = Col([Text(@Join(@GroupBy($rows, "team", "score", "sum"), "; ")), '
        'Text(@Format(1234.5, "currency", 2, "USD")), Text(@Plural(2, "item")), '
        'Text(@Pad(7, 3)), Text(@FormatDate("2024-03-05", "iso"))])'
    )
    assert "A" in html and "B" in html
    assert "1,234.50" in html
    assert "2 items" in html
    assert "007" in html
    assert "2024-03-05" in html


def test_icons_known_and_fallback() -> None:
    html = _render('root = Row([Icon("map-pin"), Icon("not-a-real-icon")], 2)')
    assert 'data-icon="map-pin"' in html
    assert 'data-icon="not-a-real-icon"' in html
    assert html.count("<svg") == 2


def test_unknown_component_degrades() -> None:
    html = _render('root = TotallyUnknown("x")')
    assert "gui-unknown" in html
    assert "TotallyUnknown" in html


def test_incomplete_statement_is_ignored() -> None:
    html = _render('broken = Col([Title("x")\nroot = Text("ok")')
    assert "ok" in html
    assert "broken" not in html


def test_missing_root_shows_empty_hint() -> None:
    html = _render('a = Title("x")')
    assert "gui-empty" in html


def test_dividers_badges_and_quote() -> None:
    html = _render(
        'root = Col([Badge("new", "success"), Divider(), Quote("stay hungry", "Jobs"), '
        'Link("site", "https://example.com"), Code("print(1)", "python")])'
    )
    assert "gui-badge-success" in html
    assert "gui-divider" in html
    assert "stay hungry" in html
    assert 'href="https://example.com"' in html
    assert "print(1)" in html
    assert "gui-code-copy" in html


def test_conditional_visibility_with_celebration() -> None:
    html = _render(
        '$done = true\nroot = Col([Celebration($done), Text($done ? "完成" : "进行中")])'
    )
    assert "gui-confetti" in html
    assert "完成" in html


KITCHEN_SINK = "\n".join(
    [
        '$q = "hi"',
        "$flag = true",
        '$date = "2024-03-05"',
        '$mode = "a"',
        "$n = 5",
        "$secs = 30",
        "root = Col([",
        '  Badge("b"), Box([Text("box")]), Button("go", @ToAssistant("go")), Caption("cap"),',
        '  Card([Text("card")]), Carousel([Text("slide")], 100), Celebration(true),',
        '  Chart("bar", [{k: "A", v: 1}], "k", ["v"]), Checkbox($flag, "check"), Circle(10, 10, 5),',
        '  Code("let a = 1", "js"), Divider(), DatePicker($date, "date"), Ellipse(20, 20, 10, 6),',
        '  Flashcard("front", "back"), Form([Input($q, "name")]), Grid([Text("grid")], 2),',
        '  HtmlView("<b>x</b>"), Icon("check"), IconButton("check", @ToAssistant("i"), "label"),',
        '  Image("https://example.com/a.png", "alt"), Input($q, "input"), Label("label"),',
        '  Line(0, 0, 10, 10), Link("link", "https://example.com"), List([ListItem("item")]),',
        '  Map([MapMarker("Paris", 48.85, 2.35), MapMarker("Lyon", 45.76, 4.83)], true),',
        '  Markdown("**m**"), Math("x^2"), Path("M0 0 L10 10"), Polygon("0,0 10,0 5,10"),',
        '  Polyline("0,0 5,5"), Popover("tip", Text("content")),',
        '  Pressable([Text("press")], @ToAssistant("p")), Quote("quote"),',
        '  RadioGroup($mode, ["a", "b"], "radio"), Rect(0, 0, 10, 10), Row([Text("row")]),',
        '  SearchImage("cat"), SegmentedControl($mode, ["a", "b"]), Select($mode, ["a", "b"]),',
        '  Slider($n, 0, 10, 1, "n"), Spacer(),',
        '  Svg([G([Circle(5, 5, 2)]), SvgText("t", 0, 10)], 20, 20),',
        '  Table(["h"], [["v"]]), Text("text"), TextArea($q), Timer($secs), Title("title"),',
        '  Audio("/agent_vm/out/voice.mp3", "旁白"), Video("/agent_vm/out/demo.mp4", null, "演示"),',
        '  YouTube("dQw4w9WgXcQ")',
        "], 2)",
    ]
)


def test_every_component_renders_without_error() -> None:
    html = _render(KITCHEN_SINK)
    assert "gui-error" not in html
    assert "gui-unknown" not in html
    for marker in (
        "gui-badge",
        "gui-box",
        "gui-btn",
        "gui-caption",
        "gui-card",
        "gui-carousel",
        "gui-confetti",
        "gui-chart-svg",
        "gui-checkbox",
        "gui-code",
        "gui-divider",
        "gui-flashcard",
        "gui-form",
        "gui-grid",
        "gui-htmlview",
        "gui-icon",
        "gui-icon-btn",
        "gui-image",
        "gui-input",
        "gui-list",
        "gui-map",
        "gui-md",
        "gui-popover",
        "gui-pressable",
        "gui-quote",
        "gui-radio-group",
        "gui-segmented",
        "gui-select",
        "gui-slider",
        "gui-spacer",
        "gui-svg",
        "gui-table",
        "gui-textarea",
        "gui-timer",
        "gui-title",
        "gui-video",
        "gui-audio",
    ):
        assert marker in html, marker


def test_map_accepts_marker_children() -> None:
    html = _render(
        'root = Map([MapMarker("Paris", 48.85, 2.35), MapMarker("Lyon", 45.76, 4.83)], true)'
    )
    assert "2 个地点" in html
    assert "Paris" in html and "Lyon" in html
    assert "<polyline" in html


def test_list_item_marker_keywords_are_not_rendered_as_text() -> None:
    html = _render(
        'root = List([ListItem("博物馆通票", "€90", "none"), ListItem("闭馆日", "周二", "none")], "none")'
    )
    assert "博物馆通票" in html and "闭馆日" in html
    assert ">none<" not in html
    assert "gui-list-item-mark" not in html
    assert "marker-none" in html


def test_list_item_custom_marker_still_renders() -> None:
    html = _render('root = List([ListItem("第一步", "说明", "1")], "none")')
    assert "gui-list-item-mark" in html
    assert ">1<" in html


def test_media_kind_and_local_url_resolution() -> None:
    media = _run(
        {
            "media": [
                "/agent_vm/out/chart.png",
                "C:\\work\\demo.mp3",
                "https://example.com/clip.mp4",
                "/agent_vm/genui/paris.genui",
                "/agent_vm/genui/paris.openui",
                "/agent_vm/genui/paris.purrcat-ui",
                "https://example.com/readme.md",
                "file:///C:/work/voice.ogg",
            ]
        }
    )["media"]
    assert [m["kind"] for m in media] == [
        "image",
        "audio",
        "video",
        "genui",
        "genui",
        "",
        "",
        "audio",
    ]
    assert [m["local"] for m in media] == [
        True,
        True,
        False,
        True,
        True,
        True,
        False,
        True,
    ]
    assert (
        media[0]["url"] == "/api/filesystem/preview?path=%2Fagent_vm%2Fout%2Fchart.png"
    )
    assert media[2]["url"] == "https://example.com/clip.mp4"
    assert "media-image" in media[0]["html"]
    assert "<audio controls" in media[1]["html"]
    assert "<video controls" in media[2]["html"]
    assert 'data-genui-file="/agent_vm/genui/paris.genui"' in media[3]["genui"]


def test_audio_and_video_components() -> None:
    html = _render(
        'root = Col([Audio("/agent_vm/out/voice.mp3", "旁白"), '
        'Video("https://example.com/demo.mp4", null, "演示")])'
    )
    assert "gui-audio" in html
    assert "/api/filesystem/preview?path=%2Fagent_vm%2Fout%2Fvoice.mp3" in html
    assert "gui-media-video" in html
    assert "<video" in html
    assert "https://example.com/demo.mp4" in html


def test_inline_color_markup() -> None:
    html = _render(
        'root = Text("营收 <green>+12%</green>，成本 <red>+3%</red>，'
        '<yellow>注意</yellow>，<danger>**重点**</danger>")'
    )
    assert html.count("gui-inline-color") == 4
    assert "var(--gui-success)" in html
    assert "var(--gui-danger)" in html
    assert "var(--gui-warning)" in html
    assert "<strong>重点</strong>" in html
    assert "<green>" not in html and "<red>" not in html


def test_unknown_inline_tag_stays_literal() -> None:
    html = _render('root = Text("比较 <b>a</b> 与 <red>ok</red>")')
    assert "&lt;b&gt;a&lt;/b&gt;" in html
    assert html.count("gui-inline-color") == 1
    assert "ok" in html

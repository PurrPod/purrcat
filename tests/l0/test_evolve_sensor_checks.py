"""Sensor 协议体检的静态检查与报告块纯逻辑（SPEC-020）。

锁定拆分前 `sensor/evaluator.py` 的检查项顺序、字段集合、失败文案与报告块
组装口径；运行时夹具只验证导入面与初始快照，不拉起真实子进程。
"""

from __future__ import annotations

from src.evolve.sensor import checks_static, evaluator, fixtures


def _sensor_script(with_issues: bool = False) -> str:
    if with_issues:
        return (
            "import os\n"
            "import sys\n"
            "TOKEN = os.environ.get('MY_TOKEN')\n"
            "API_KEY = '0123456789abcdef0123'\n"
            "sys.exit(1)\n"
        )
    return (
        "# /// script\n"
        "# ///\n"
        "import os\n"
        "import sys\n"
        "sys.stdout = sys.stderr\n"
        "TOKEN = os.environ.get('MY_TOKEN')\n"
    )


def test_static_check_order_fields_and_green_details():
    """SPEC-020 AC-1：检查项 id 顺序、字段集合与全绿文案逐字不变。"""
    cases = checks_static.static_checks(
        _sensor_script(), {"name": "demo", "env": {"MY_TOKEN": ""}}, "", "demo"
    )

    assert [case["id"] for case in cases] == [
        "pep723",
        "stdout_redirect",
        "no_force_exit",
        "no_hardcoded_secret",
        "config_valid",
        "env_declared",
    ]
    assert all(case["layer"] == "L0" for case in cases)
    assert all(
        set(case) == {"id", "layer", "title", "pass", "detail", "level"}
        for case in cases
    )
    by_id = {case["id"]: case for case in cases}
    assert by_id["pep723"]["detail"] == "已声明内联依赖块"
    assert (
        by_id["stdout_redirect"]["detail"] == "日志已改道 stderr，协议通道独占 stdout"
    )
    assert by_id["no_force_exit"]["detail"] == "未发现 sys.exit / os._exit"
    assert by_id["no_hardcoded_secret"]["detail"] == "未发现疑似硬编码密钥"
    assert (
        by_id["config_valid"]["detail"] == "name='demo'（应为 'demo'），env 为对象=True"
    )
    assert (
        by_id["env_declared"]["detail"] == "代码与 sensor_config.json 的 env 键集一致"
    )


def test_static_check_violation_details_are_verbatim():
    """SPEC-020 AC-1：违规分支的定位文案（含调用片段与截断）不变。"""
    config = {"name": "other", "env": {"MY_TOKEN": "", "UNUSED": ""}}
    cases = checks_static.static_checks(_sensor_script(True), config, "", "demo")
    by_id = {case["id"]: case for case in cases}

    assert (
        by_id["pep723"]["detail"] == "缺少 `# /// script` 内联依赖块，uv run 无法建环境"
    )
    assert (
        by_id["stdout_redirect"]["detail"]
        == "未见 `sys.stdout = sys.stderr`，print 日志会污染协议通道"
    )
    assert (
        by_id["no_force_exit"]["detail"]
        == "发现强制退出调用 `sys.exit(`，违反「严禁退出主进程」铁律"
    )
    assert (
        by_id["no_hardcoded_secret"]["detail"]
        == "疑似硬编码密钥: `API_KEY = '0123456789abcdef0123'...`"
    )
    assert by_id["env_unused"]["level"] == "warn"
    assert (
        by_id["env_unused"]["detail"] == "sensor_config.json 声明了但代码未读取：UNUSED"
    )


def test_static_check_undeclared_env_message():
    """SPEC-020 AC-1：代码读取但未声明的环境变量文案不变。"""
    cases = checks_static.static_checks(
        _sensor_script(), {"name": "demo", "env": {}}, "", "demo"
    )
    by_id = {case["id"]: case for case in cases}

    assert by_id["env_declared"]["pass"] is False
    assert (
        by_id["env_declared"]["detail"]
        == "代码读取了未声明的环境变量：MY_TOKEN，合并后用户无法在配置中心填写"
    )


def test_static_check_config_error_is_passed_through():
    """SPEC-020 AC-1：配置解析错误原样进入 config_valid，且声明集合为空。"""
    cases = checks_static.static_checks(_sensor_script(), {}, "JSON 解析失败", "demo")
    by_id = {case["id"]: case for case in cases}

    assert by_id["config_valid"]["pass"] is False
    assert by_id["config_valid"]["detail"] == "JSON 解析失败"
    assert by_id["env_declared"]["pass"] is False


def test_summarize_cases_keeps_four_counts_only():
    """SPEC-020 AC-2：报告计数只暴露 passed/total/errors/warnings。"""
    cases = [
        {"pass": True, "level": "error"},
        {"pass": False, "level": "error"},
        {"pass": False, "level": "warn"},
    ]
    assert evaluator._summarize_cases(cases) == {
        "passed": 1,
        "total": 3,
        "errors": 1,
        "warnings": 1,
    }


class _FakeH:
    """记录报告 DSL 调用，避免引入 HTML 渲染器。"""

    def __init__(self):
        self.sections = []

    def cases(self, items):
        return {"cases": items}

    def bullets(self, items):
        return {"bullets": items}

    def section(self, number, title, body):
        block = {"number": number, "title": title, "body": body}
        self.sections.append(block)
        return block


def test_layer_blocks_keep_order_numbering_and_status_mapping():
    """SPEC-020 AC-2：L0/L1 分层块编号、状态映射与备注来源不变。"""
    cases = [
        {"layer": "L0", "title": "a", "pass": True, "level": "error", "detail": "da"},
        {"layer": "L0", "title": "b", "pass": False, "level": "warn", "detail": "db"},
        {"layer": "L1", "title": "c", "pass": False, "level": "error", "detail": "dc"},
    ]
    helper = _FakeH()

    blocks, next_no = evaluator._build_layer_blocks(cases, 1, helper)

    assert [block["title"] for block in blocks] == ["L0 静态契约", "L1 协议夹具"]
    assert [block["number"] for block in blocks] == ["01", "02"]
    assert next_no == 3
    l0_items = blocks[0]["body"]["cases"]
    assert [(item["status"], item["badge_text"]) for item in l0_items] == [
        ("pass", "通过"),
        ("warn", "告警"),
    ]
    assert blocks[1]["body"]["cases"][0]["status"] == "fail"
    assert blocks[1]["body"]["cases"][0]["notes"] == ["dc"]


def test_uncovered_block_appends_local_source_hint_only_for_local():
    """SPEC-020 AC-2：未覆盖项固定 6 条，source=local 时追加一条提示。"""
    helper = _FakeH()

    plain = evaluator._build_uncovered_block({}, 3, helper)
    local = evaluator._build_uncovered_block({"source": "local"}, 3, helper)

    assert plain["number"] == "03"
    assert len(plain["body"]["bullets"]) == 6
    assert len(local["body"]["bullets"]) == 7
    assert local["body"]["bullets"][-1].startswith("该 sensor 声明 source: local")


def test_load_config_branches(tmp_path):
    """SPEC-020 AC-2：配置缺失 / 损坏 / 非对象三种错误文案不变。"""
    missing, missing_error = evaluator._load_config(str(tmp_path / "missing.json"))
    assert missing == {}
    assert missing_error == "沙盒内未找到 sensor_config.json（合并注册的唯一依据）"

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    _, broken_error = evaluator._load_config(str(broken))
    assert broken_error.startswith("sensor_config.json JSON 解析失败: ")

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    _, array_error = evaluator._load_config(str(array))
    assert array_error == "sensor_config.json 顶层必须是对象"

    good = tmp_path / "good.json"
    good.write_text('{"name": "demo"}', encoding="utf-8")
    assert evaluator._load_config(str(good)) == ({"name": "demo"}, "")


def test_evaluator_reexports_checks_and_fixture_snapshot():
    """SPEC-020 AC-1：旧入口仍可用，夹具未启动时快照为空且不存活。"""
    assert evaluator._static_checks is checks_static.static_checks
    fixture = fixtures._GatewayFixture("s.py", ".", {}, "stderr.log")
    assert fixture.snapshot() == ([], [], [])
    assert fixture.alive() is False
    assert fixtures.FIXTURE_SESSION_ID == "SID_TEST"

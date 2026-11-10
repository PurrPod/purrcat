"""Evolve 提示词/指南/脚手架模板的逐字锁定（SPEC-013）。"""

from __future__ import annotations

import hashlib

from src.evolve.agentloop import factory as agentloop_factory
from src.evolve.agentloop.guide_generator import generate_agentloop_guide
from src.evolve.graph import factory as graph_factory
from src.evolve.graph.guide_generator import generate_graph_guide
from src.evolve.mcp.guide_generator import generate_mcp_guide
from src.evolve.sensor import factory as sensor_factory
from src.evolve.sensor.guide_generator import generate_sensor_guide
from src.evolve.skill.guide_generator import generate_skill_guide
from src.evolve.skill.prompts import build_expected_output_prompt
from src.evolve.ui_plugin import factory as ui_plugin_factory
from src.evolve.ui_plugin.guide_generator import generate_ui_plugin_guide


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_guide_outputs_are_byte_identical():
    # 重构只允许搬动模板，不允许改写内容；哈希即逐字锁。
    assert _sha(generate_sensor_guide("demo")) == (
        "c831924671039b27f365b6fc8c2bdd8f2c2df0a5e9c17e701877b8d84975932f"
    )
    assert _sha(generate_skill_guide("demo")) == (
        "dac1839b391234533b4537d3bd1f749b8fea326e59e861d33649e59361c044d9"
    )
    assert _sha(generate_mcp_guide("demo", "", "D:/vm")) == (
        "f3c087b3e3c7f98fc747464266a7deaa6b068fc40fb60084487687f449a6e636"
    )
    assert _sha(generate_graph_guide("demo")) == (
        "45add66cf7e181df18ea35619b32c9172b73a7483442fceb8938e1f06afafc8c"
    )
    assert _sha(generate_agentloop_guide("demo")) == (
        "0794d6b74284f7692397a080ec2705e2e248141ea29113adcf39d66f308578be"
    )
    assert _sha(
        generate_ui_plugin_guide("demo", "Demo", "panel", "D:/vm/ui-plugin/demo")
    ) == ("4034d15e458c9c3f59fe0ae9925ed825270b42d2e0e0eafe64734f2025f7b839")


def test_goal_is_injected_into_every_guide():
    goal = "构建一个演示目标"
    assert goal in generate_sensor_guide("demo", goal)
    assert goal in generate_skill_guide("demo", goal)
    assert goal in generate_mcp_guide("demo", goal)
    assert goal in generate_graph_guide("demo", goal)
    assert goal in generate_agentloop_guide("demo", goal)
    assert goal in generate_ui_plugin_guide(
        "demo", "Demo", "panel", "D:/vm/ui-plugin/demo", goal
    )


def test_skill_eval_prompt_keeps_order_and_checklist_format():
    prompt = build_expected_output_prompt("预期结果", ["断言一", "断言二"])
    assert prompt == (
        "【预期结果】\n预期结果\n\n【硬性断言检查清单(Assertions)】\n- 断言一\n- 断言二"
    )


def test_generated_scaffolds_are_byte_identical():
    assert _sha(sensor_factory._skeleton("demo")) == (
        "8b556b1ff1ff3c6410495052414159231a86ad8e40f17e8a4e5b1c7740267e91"
    )
    assert _sha(sensor_factory._config_template("demo")) == (
        "0f68a0a0b14b13811f486901c53b354e06030cd0c0b134fb36ba4a5d275182cb"
    )
    assert _sha(sensor_factory._gateway_probe()) == (
        "2447e17cf7b7fc99d0e613fca143afaf98e23342f2e0407805e03e276d07f605"
    )
    assert _sha(agentloop_factory._skeleton("demo")) == (
        "66485f74fa9d76d04f8710dd79994b0ff30de1e085b62715e51ee84a26e43731"
    )
    # graph 骨架是 dict，逐字锁用序列化文本。
    assert _sha(str(graph_factory._skeleton("demo"))) == (
        "bf02c9d7e6507289282e4102a8fada6f1f2a7ed717db79109ba9593d59b20fd8"
    )
    assert _sha(ui_plugin_factory.INDEX_HTML_TPL) == (
        "b951e07173b1f80ac23f27db79a72fff43b1e38fd396d4e85420b77575bba0cd"
    )

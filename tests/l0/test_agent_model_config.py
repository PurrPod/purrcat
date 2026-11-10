"""AgentModel 的配置映射与 API Key 选择（SPEC-009）。"""

from __future__ import annotations

from src.model.facade.model import AgentModel


def test_pick_api_key_prefers_single_key_then_first_valid_list_entry():
    assert AgentModel._pick_api_key({"api_key": "single"}) == "single"
    assert (
        AgentModel._pick_api_key({"api_keys": ["", "  ", "first", "second"]}) == "first"
    )
    assert AgentModel._pick_api_key({}) is None
    assert AgentModel._pick_api_key({"api_keys": []}) is None


def test_apply_model_config_sets_vision_and_fields():
    model = AgentModel.__new__(AgentModel)

    model._apply_model_config(
        "m1",
        {"base_url": "http://x", "api_keys": ["k"], "vision": True},
    )

    assert model.model_name == "m1"
    assert model.base_url == "http://x"
    assert model.api_key == "k"
    assert model.vision is True

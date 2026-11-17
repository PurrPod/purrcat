"""Graph 进化工厂拒绝内置 default 图（SPEC-037）。"""

from src.evolve.graph.factory import graph_factory_init, graph_request_handle


def test_factory_rejects_default_upgrade() -> None:
    message, workplace_id = graph_factory_init("default", True)

    assert "内置图" in message
    assert workplace_id == ""


def test_factory_rejects_default_create() -> None:
    message, workplace_id = graph_factory_init("default", False)

    assert "内置图" in message
    assert workplace_id == ""


def test_merge_rejects_default() -> None:
    message = graph_request_handle("unused-workplace", "default", True)

    assert "内置图" in message

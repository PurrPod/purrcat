"""Graph 进化工厂拒绝内置图（SPEC-037 / SPEC-040）。"""

import pytest

from src.evolve.graph.factory import graph_factory_init, graph_request_handle
from src.harness.graph_init import BUILTIN_GRAPH_NAMES


@pytest.mark.parametrize("name", BUILTIN_GRAPH_NAMES)
def test_factory_rejects_builtin_upgrade(name: str) -> None:
    message, workplace_id = graph_factory_init(name, True)

    assert "内置图" in message
    assert workplace_id == ""


@pytest.mark.parametrize("name", BUILTIN_GRAPH_NAMES)
def test_factory_rejects_builtin_create(name: str) -> None:
    message, workplace_id = graph_factory_init(name, False)

    assert "内置图" in message
    assert workplace_id == ""


@pytest.mark.parametrize("name", BUILTIN_GRAPH_NAMES)
def test_merge_rejects_builtin(name: str) -> None:
    message = graph_request_handle("unused-workplace", name, True)

    assert "内置图" in message

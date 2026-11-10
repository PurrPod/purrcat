"""模型契约：测试替身与真实实现的调用签名必须一致（SPEC-002）。"""

from __future__ import annotations

import inspect

import pytest

from src.model.facade.model import Model
from tests.support.fakes import FakeModel


def _params(func) -> dict[str, inspect.Parameter]:
    return dict(inspect.signature(func).parameters)


def _required_names(params: dict[str, inspect.Parameter]) -> list[str]:
    kinds = {
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    }
    return [
        name
        for name, param in params.items()
        if param.default is inspect.Parameter.empty and param.kind in kinds
    ]


def test_fake_model_chat_required_params_match_model_chat():
    assert _required_names(_params(FakeModel.chat)) == _required_names(
        _params(Model.chat)
    )


def test_fake_model_chat_accepts_every_model_chat_param():
    assert set(_params(Model.chat)) <= set(_params(FakeModel.chat))


@pytest.mark.parametrize("method", ["bind_task", "unbind"])
def test_fake_model_mirrors_model_lifecycle_methods(method):
    assert callable(getattr(FakeModel, method, None))
    assert _required_names(_params(getattr(FakeModel, method))) == _required_names(
        _params(getattr(Model, method))
    )

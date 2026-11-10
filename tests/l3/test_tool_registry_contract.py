"""工具注册契约：schema 只需保证可调用，不要求与函数签名相等（SPEC-003）。"""

from __future__ import annotations

import inspect

import pytest

from src.tool import AGENT_TOOL_SCHEMA
from src.tool.utils.route import (
    PROCESS_ISOLATED_TOOLS,
    SYSTEM_INJECTED_ARGUMENTS,
    TOOL_FUNC_MAP,
    resolve_tool,
)

SCHEMAS = [entry.get("function", entry) for entry in AGENT_TOOL_SCHEMA]
TOOL_NAMES = [schema["name"] for schema in SCHEMAS]
VARIADIC_KINDS = (
    inspect.Parameter.VAR_KEYWORD,
    inspect.Parameter.VAR_POSITIONAL,
)


def _properties(schema: dict) -> set[str]:
    return set(schema.get("parameters", {}).get("properties", {}))


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_exposed_tool_resolves_to_callable(name):
    assert callable(resolve_tool(name))


def test_registered_tools_match_tools_exposed_to_model():
    registered = {name.lower() for name in TOOL_FUNC_MAP}
    exposed = {name.lower() for name in TOOL_NAMES}

    assert registered == exposed, (
        f"仅注册未暴露: {sorted(registered - exposed)}；"
        f"仅暴露未注册: {sorted(exposed - registered)}"
    )


@pytest.mark.parametrize("schema", SCHEMAS, ids=TOOL_NAMES)
def test_schema_properties_are_accepted_by_function(schema):
    params = inspect.signature(resolve_tool(schema["name"])).parameters
    accepts_extra = any(
        param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values()
    )
    unaccepted = _properties(schema) - set(params)

    assert not unaccepted or accepts_extra, (
        f"{schema['name']} 的 schema 参数 {sorted(unaccepted)} "
        "既不是函数形参，函数也没有接收 **kwargs"
    )


@pytest.mark.parametrize("schema", SCHEMAS, ids=TOOL_NAMES)
def test_required_function_params_are_reachable(schema):
    params = inspect.signature(resolve_tool(schema["name"])).parameters
    required = {
        name
        for name, param in params.items()
        if param.default is inspect.Parameter.empty and param.kind not in VARIADIC_KINDS
    }
    unreachable = required - _properties(schema) - SYSTEM_INJECTED_ARGUMENTS

    assert not unreachable, (
        f"{schema['name']} 的必填参数 {sorted(unreachable)} "
        "既不由模型提供，也不在系统注入白名单里"
    )


def test_system_injected_arguments_are_frozen():
    assert SYSTEM_INJECTED_ARGUMENTS == {
        "session_id",
        "_is_sub_branch",
        "_session_id",
        "_request_bytes",
        "_request_limit_bytes",
        "_tool_call_id",
        "_vision_mode",
    }


def test_process_isolation_whitelist_is_frozen():
    assert PROCESS_ISOLATED_TOOLS == {"bash", "fetch", "request", "search"}

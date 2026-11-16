"""Graph 消息卡片语义（SPEC-030）。"""

from __future__ import annotations

import asyncio
import json

from src.harness.node.extensions.message_card_builder.node import Node


def _run(inputs: dict) -> dict:
    return asyncio.run(Node("card", {}).execute(inputs, None))


def test_wraps_content_as_workflow_input_card():
    result = _run({"content": "把这件事做完"})

    message = result["message_list"][0]
    assert message["role"] == "user"
    assert json.loads(message["content"]) == {
        "type": "workflow_input",
        "content": "把这件事做完",
    }


def test_role_input_is_no_longer_accepted():
    result = _run({"content": "hi", "role": "system"})

    message = result["message_list"][0]
    assert message["role"] == "user"


def test_empty_content_returns_empty_list():
    assert _run({"content": ""}) == {"message_list": []}

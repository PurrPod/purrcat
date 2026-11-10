"""工具执行器：同步/异步调用、打断与错误传播（SPEC-007）。"""

from __future__ import annotations

import asyncio
import queue
import threading

import pytest

from src.tool.utils.execution import (
    execute_inline,
    execute_tool,
    interrupted_result,
    process_worker,
    run_func_sync,
)


def test_run_func_sync_supports_sync_and_async_tools():
    assert run_func_sync(lambda x: x + 1, {"x": 1}) == 2

    async def async_tool(x):
        await asyncio.sleep(0)
        return x * 2

    assert run_func_sync(async_tool, {"x": 3}) == 6


def test_process_worker_reports_success_and_error():
    result_queue = queue.Queue()
    process_worker(lambda x: x + 1, {"x": 1}, result_queue)
    assert result_queue.get() == {"status": "success", "data": 2}

    def boom(**kwargs):
        raise RuntimeError("炸了")

    process_worker(boom, {}, result_queue)
    assert result_queue.get() == {"status": "error", "error": "RuntimeError: 炸了"}


def test_execute_inline_propagates_tool_error():
    def boom(**kwargs):
        raise ValueError("bad")

    with pytest.raises(ValueError, match="bad"):
        execute_inline(boom, {}, None)


def test_execute_inline_returns_interrupted_result_when_cancelled():
    import time

    cancel = threading.Event()
    cancel.set()

    def slow_tool():
        time.sleep(0.3)
        return "never"

    result = execute_inline(slow_tool, {}, cancel)

    assert result == interrupted_result()
    assert "人类打断" in result["content"]


def test_execute_tool_routes_to_inline_by_default():
    assert execute_tool(lambda: "ok", {}) == "ok"

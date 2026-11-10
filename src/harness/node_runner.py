"""单个 DAG 节点的执行包装。

固定顺序：后台线程组装输入 → 执行节点 → 后台线程落盘输出；
异常原样上抛，由主循环统一置 ERROR。
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable


async def execute_node(
    node_id: str,
    node_instance: Any,
    *,
    context: Any,
    build_inputs: Callable[[str], dict],
    save_outputs: Callable[[str, dict], None],
):
    # 1. 后台线程组装胖输入
    inputs = await asyncio.to_thread(build_inputs, node_id)
    # 2. 执行节点业务
    result = await node_instance.execute(inputs, context=context)
    # 3. 后台线程落盘胖输出
    await asyncio.to_thread(save_outputs, node_id, result)
    return result

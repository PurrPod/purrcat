"""KernelUpgrade 工具主入口：按 action 分发到 create / upgrade / merge / test"""

import traceback

from src.tool.utils.format import error_response
from .shared import ACTIONS, TYPES
from .create import create_module
from .upgrade import upgrade_module
from .merge import merge_module
from .test import test_module


def KernelUpgrade(action: str, type: str, target: str, **kwargs) -> dict:
    """
    Agent 的自我进化内核工具。

    - action="create" : 在隔离沙盒中搭建某 type 的全新骨架
    - action="upgrade": 把正式区里已存在的该 type 对象（含配置）搬进沙盒
    - action="merge"  : 代发合并审批请求（相当于原 Request 的 *_merge）
    - action="test"   : 代发架构级测试（skill/sensor 走审批队列，mcp 直接后台评测）

    type ∈ {skill, mcp, sensor, graph, agentloop, ui-plugin}
    target: 一般为名字；merge/test 时为沙盒前缀 "uuid/名字"
    """
    try:
        act = (action or "").strip()
        t = (type or "").strip()
        tgt = (target or "").strip()

        if act not in ACTIONS:
            return error_response(
                f"不支持的 action: {action}（可选：{'、'.join(ACTIONS)}）",
                "参数错误",
            )
        if t not in TYPES:
            return error_response(
                f"不支持的 type: {type}（可选：{'、'.join(TYPES)}）",
                "参数错误",
            )
        if not tgt:
            return error_response("target 不能为空", "参数错误")

        if act == "create":
            return create_module(t, tgt)
        if act == "upgrade":
            return upgrade_module(t, tgt)
        if act == "merge":
            return merge_module(t, tgt)
        return test_module(t, tgt)

    except Exception as e:
        traceback.print_exc()
        return error_response(f"KernelUpgrade 执行异常: {str(e)}", "执行失败")

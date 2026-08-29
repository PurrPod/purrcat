"""
Skill 与 MCP 进化工厂模块 (evolve/__init__.py)

采用纯沙盒拷贝模式，从架构层面切断所有潜在风险。
Agent 在完全独立的 UUID 沙盒中工作，折腾坏了直接删，折腾好了由宿主机负责接管、Diff、合并和 Commit。

核心 API:
- skill_improve_init: 初始化 Skill 进化沙盒
- skill_generate_diff: 生成差异对比（供人类审批参考）
- skill_request_handle: 处理人类审批
- skill_rollback: 安全回滚
- run_skill_eval_background: 自动化 Skill 沙盒测试
- mcp_improve_init: 初始化 MCP Server 沙盒
- run_mcp_eval_background: 自动化 MCP 并发测试

架构优势：
1. 沙盒隔离：利用 uuid 在 agent_vm/skill_workplace/ 和 agent_vm/mcp_workplace/ 内创建完全独立的测试/升级区
2. 纯拷贝模式：不挂载真实主库，彻底切断安全风险
3. 渐进式指导：通过内置生成的规范指南文档充当隐式的 Agent Prompt
4. 版本控制自动化：自动接管 Git 仓库的初始化、追踪与标准化 Commit Message 生成
5. 完整的 Git Flow：Fork → Pull Request → Merge → Revert
6. 自动化测试：后台执行 evals，生成完整的 eval_report.md / test_report.md 报告
"""

from .skill.factory import (
    skill_improve_init,
    skill_generate_diff,
    skill_request_handle,
    skill_rollback,
)
from .skill.evaluator import (
    run_skill_eval_background,
    run_skill_trigger_eval_background,
)
from .mcp.factory import mcp_improve_init, mcp_upgrade_init, mcp_request_handle
from .mcp.evaluator import run_mcp_eval_background
from .sensor.factory import sensor_factory_init, sensor_request_handle

__all__ = [
    "skill_improve_init",
    "skill_generate_diff",
    "skill_request_handle",
    "skill_rollback",
    "run_skill_eval_background",
    "run_skill_trigger_eval_background",
    "mcp_improve_init",
    "mcp_upgrade_init",
    "run_mcp_eval_background",
    "mcp_request_handle",
    "sensor_factory_init",
    "sensor_request_handle",
]

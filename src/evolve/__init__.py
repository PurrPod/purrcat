"""
Skill 进化工厂模块 (evolve/__init__.py)

采用纯沙盒拷贝模式，从架构层面切断所有潜在风险。
Agent 在完全独立的 UUID 沙盒中工作，折腾坏了直接删，折腾好了由宿主机负责接管、Diff、合并和 Commit。

核心 API:
- skill_improve_init: 初始化进化沙盒
- skill_generate_diff: 生成差异对比（供人类审批参考）
- skill_request_handle: 处理人类审批
- skill_rollback: 安全回滚
- run_skill_eval_background: 自动化沙盒测试

架构优势：
1. 沙盒隔离：利用 uuid 在 agent_vm/skill_workplace/ 内创建完全独立的测试/升级区
2. 纯拷贝模式：不挂载真实主库，彻底切断安全风险
3. 渐进式指导：通过内置生成的规范 README.md 充当隐式的 Agent Prompt
4. 版本控制自动化：自动接管 Git 仓库的初始化、追踪与标准化 Commit Message 生成
5. 完整的 Git Flow：Fork → Pull Request → Merge → Revert
6. 自动化测试：后台执行 evals，生成完整的 eval_report.md 报告
"""

from .skill.factory import skill_improve_init, skill_generate_diff, skill_request_handle, skill_rollback
from .skill.readme_generator import generate_factory_readme
from .skill.evaluator import run_skill_eval_background

__all__ = [
    "skill_improve_init",
    "skill_generate_diff",
    "skill_request_handle",
    "skill_rollback",
    "generate_factory_readme",
    "run_skill_eval_background",  # 暴露给 Request 使用
]
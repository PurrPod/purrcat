"""
AgentLoop 进化工厂核心逻辑 (evolve/agentloop/factory.py)

单文件沙盒模式：AgentLoop 本体是单个 <name>.yaml，
沙盒内配套 evals/validate.py 做「格式 / 功能 / 关键词汇」三重校验，
合并时系统会宿主侧重跑同一套校验，全绿才允许写入正式 paradigms 目录。
"""

import os
import shutil
import uuid
from datetime import datetime

from src.evolve.common.git import commit_paths, ensure_git_repo
from src.evolve.common.names import safe_name
from src.evolve.common.templates import write_goal_and_guide, write_sandbox_validator
from src.evolve.common.validation import validation_summary
from src.utils.config import PARADIGMS_DIR, AGENT_VM_DIR

from . import validator as _validator
from .guide_generator import generate_agentloop_guide
from .validator import validate_agentloop_file

WORKPLACE_KIND = "agentloop_workplace"


def _safe_name(name: str) -> str:
    return safe_name(name, "AgentLoop", strip_suffixes=(".yaml", ".yml"))


def _skeleton(name: str, goal: str = "") -> str:
    """全新 AgentLoop 的最小可运行骨架（合法且不改变默认行为）"""
    desc = goal.strip().splitlines()[0] if goal.strip() else f"{name} 自定义主循环"
    return f"""name: "{name}"
description: "{desc}"
description-en: "A custom agent loop paradigm."
path: agent_vm
loop_end_max_retry: 3
hooks:
  on_build_system_prompt:
    - injection:
        content: "@RULES"
"""


def _write_sandbox(root: str, name: str, goal: str):
    """写 GOAL.md / GUIDE.md / evals/validate.py。"""
    write_goal_and_guide(root, goal, generate_agentloop_guide(name, goal))

    evals_dir = os.path.join(root, "evals")
    os.makedirs(evals_dir, exist_ok=True)
    write_sandbox_validator(_validator, os.path.join(evals_dir, "validate.py"))


def agentloop_factory_init(
    name: str, is_upgrade: bool, goal: str = ""
) -> tuple[str, str]:
    """初始化 AgentLoop 进化沙盒，返回 (系统提示, workplace_id)"""
    try:
        base = _safe_name(name)
    except ValueError as e:
        return f"❌ {e}", ""

    short_uuid = uuid.uuid4().hex[:5]
    workplace_root = os.path.join(AGENT_VM_DIR, WORKPLACE_KIND, short_uuid)
    yaml_path = os.path.join(workplace_root, f"{base}.yaml")

    if os.path.exists(workplace_root):
        shutil.rmtree(workplace_root, ignore_errors=True)
    os.makedirs(workplace_root, exist_ok=True)

    if is_upgrade:
        source = os.path.join(PARADIGMS_DIR, f"{base}.yaml")
        if not os.path.exists(source):
            return f"❌ 无法执行升级：正式目录中未找到 '{base}.yaml'。", ""
        shutil.copy2(source, yaml_path)
        action_msg = f"已将现有的 '{base}.yaml' 拷贝至进化沙盒进行升级"
    else:
        with open(yaml_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(_skeleton(base, goal))
        action_msg = f"已为你搭建了全新的 '{base}' 范式骨架"

    _write_sandbox(workplace_root, base, goal)

    sandbox_root = f"/agent_vm/{WORKPLACE_KIND}/{short_uuid}"
    return (
        f"【AgentLoop 工厂分配成功】工作区路径：{sandbox_root}（workplace_id: {short_uuid}）。\n"
        f"{action_msg}。\n"
        f"💡 系统已在沙盒根目录生成官方说明文档 GUIDE.md（含阶段/动作词汇表），动手前请先通读！\n"
        f"🧪 自测脚本：`evals/validate.py`，在沙盒根目录执行 `uv run evals/validate.py` 即可完成"
        f"格式 / 功能 / 关键词汇三重校验（结论写入 evals/outputs/validation.json）。\n"
        f'🔀 校验全绿后，用 KernelUpgrade(action="merge", type="agentloop", target="{short_uuid}/{base}") 申请合并。'
    ), short_uuid


def _latest_validation_ok(workplace_root: str, name: str) -> tuple[bool, str]:
    """宿主侧重跑同一套校验（防篡改），返回 (是否通过, 结论文本)。"""
    yaml_path = os.path.join(workplace_root, f"{name}.yaml")
    if not os.path.exists(yaml_path):
        return False, f"沙盒中未找到 '{name}.yaml'"
    report = validate_agentloop_file(yaml_path, expected_name=name)
    return validation_summary(report)


def agentloop_request_handle(workplace_root: str, name: str, is_approved: bool) -> str:
    """处理 AgentLoop 合并请求：宿主侧校验 + 拷贝 paradigms 目录 + Git 提交"""
    if not is_approved:
        return f"人类拒绝了 {name} 的合并请求，已保留当前工作区供调整。"

    try:
        base = _safe_name(name)
    except ValueError as e:
        return f"❌ 合并失败：{e}"

    # 0. 宿主侧权威校验：格式/功能/关键词汇必须全绿
    verdict_ok, verdict_text = _latest_validation_ok(workplace_root, base)
    if not verdict_ok:
        return (
            f"❌ 合并被阻止：{verdict_text}。\n"
            f"请在沙盒内执行 `uv run evals/validate.py` 修复全部 error 项后再申请合并。"
        )

    source_path = os.path.join(workplace_root, f"{base}.yaml")
    os.makedirs(PARADIGMS_DIR, exist_ok=True)
    target_path = os.path.join(PARADIGMS_DIR, f"{base}.yaml")
    is_upgrade = os.path.exists(target_path)
    shutil.copy2(source_path, target_path)

    # Git 版本接管（首次自动 init）
    ensure_git_repo(PARADIGMS_DIR, "__pycache__/\n*.pyc\n")
    commit_msg = (
        f"{'upgrade' if is_upgrade else 'add'} agentloop {base} "
        f"{datetime.now().strftime('%Y-%m-%d')}"
    )
    commit_paths(PARADIGMS_DIR, [f"{base}.yaml"], commit_msg)

    default_note = (
        "\n⚠️ 你覆盖的是**默认范式 PARADIGM.yaml**，它会在新会话立即生效；若行为异常请在沙盒回滚。"
        if base.lower() == "paradigm"
        else ""
    )
    return (
        f"🎉 审批通过！AgentLoop '{base}' 成功合并。\n"
        f"📁 正式路径: {target_path}\n"
        f"🔍 校验: {verdict_text}\n"
        f"Git: {commit_msg}{default_note}"
    )


__all__ = ["agentloop_factory_init", "agentloop_request_handle"]

"""
Graph 进化工厂核心逻辑 (evolve/graph/factory.py)

文件夹沙盒模式：Graph 本体是 <name>/ 文件夹（graph.json + asset/），
沙盒内配套 evals/validate.py 做「格式 / 功能 / 关键词汇」三重校验，
合并时系统会宿主侧重跑同一套校验，全绿才允许写入正式 graph 目录。
"""

import json
import os
import shutil
import uuid
from datetime import datetime

from src.evolve.common.git import commit_paths, ensure_git_repo
from src.evolve.common.names import safe_name
from src.evolve.common.templates import write_goal_and_guide, write_sandbox_validator
from src.evolve.common.validation import validation_summary
from src.utils.config import GRAPHS_DIR, AGENT_VM_DIR

from . import validator as _validator
from .guide_generator import generate_graph_guide
from .validator import validate_graph_folder

WORKPLACE_KIND = "graph_workplace"


def _safe_name(name: str) -> str:
    return safe_name(name, "Graph")


def _skeleton(name: str, goal: str = "") -> dict:
    """全新 Graph 的最小可用骨架（渲染问候语并交给智能体循环）"""
    zh = (
        goal.strip().splitlines()[0] if goal.strip() else "渲染问候语并交给智能体循环。"
    )
    return {
        "version": "2.0",
        "name": name,
        "description": f"Render a greeting and hand it to an agent loop. ({name})",
        "description-zh": zh,
        "global_schema": {
            "name": {"type": "string", "required": True, "description": "称呼"}
        },
        "nodes": [
            {
                "id": "in",
                "type": "task_input",
                "name": "全局输入",
                "position": [-400, 0],
                "config": {"global_vars": [{"name": "name", "required": True}]},
            },
            {
                "id": "tpl_text",
                "type": "string",
                "name": "模板内容",
                "position": [-350, -180],
                "config": {"value": "你好 {{name}}，请做一次自我介绍。"},
            },
            {
                "id": "tpl",
                "type": "template_renderer",
                "name": "组装指令",
                "position": [-100, 0],
                "config": {},
            },
            {
                "id": "card",
                "type": "message_card_builder",
                "name": "构建消息",
                "position": [200, 0],
                "config": {"role": "user"},
            },
            {
                "id": "al_text",
                "type": "string",
                "name": "范式-AgentLoop",
                "position": [500, -200],
                "config": {
                    "value": (
                        'name: "graph_skeleton"\n'
                        'description: "Minimal agent loop for the graph skeleton."\n'
                        "loop_end_max_retry: 3\n"
                        "hooks:\n"
                        "  on_build_system_prompt:\n"
                        "    - injection:\n"
                        '        content: "这是一句系统提示词"\n'
                    )
                },
            },
            {
                "id": "loop",
                "type": "agent_loop",
                "name": "智能体循环",
                "position": [500, 0],
                "config": {},
            },
            {
                "id": "out",
                "type": "task_output",
                "name": "全局输出",
                "position": [800, 0],
                "config": {"target_vars": [{"name": "reply"}]},
            },
        ],
        "edges": [
            {
                "source": "in",
                "target": "tpl",
                "sourceHandle": "name",
                "targetHandle": "name",
            },
            {
                "source": "tpl_text",
                "target": "tpl",
                "sourceHandle": "text",
                "targetHandle": "template",
            },
            {
                "source": "tpl",
                "target": "card",
                "sourceHandle": "rendered_text",
                "targetHandle": "content",
            },
            {
                "source": "card",
                "target": "loop",
                "sourceHandle": "message_list",
                "targetHandle": "messages",
            },
            {
                "source": "al_text",
                "target": "loop",
                "sourceHandle": "text",
                "targetHandle": "agentloop",
            },
            {
                "source": "loop",
                "target": "out",
                "sourceHandle": "summary",
                "targetHandle": "reply",
            },
        ],
    }


def _write_sandbox(root: str, graph_dir: str, name: str, goal: str):
    """写 GOAL.md / GUIDE.md / <name>/evals/validate.py。"""
    write_goal_and_guide(root, goal, generate_graph_guide(name, goal))

    evals_dir = os.path.join(graph_dir, "evals")
    os.makedirs(evals_dir, exist_ok=True)
    write_sandbox_validator(_validator, os.path.join(evals_dir, "validate.py"))


def graph_factory_init(name: str, is_upgrade: bool, goal: str = "") -> tuple[str, str]:
    """初始化 Graph 进化沙盒，返回 (系统提示, workplace_id)"""
    try:
        base = _safe_name(name)
    except ValueError as e:
        return f"❌ {e}", ""

    short_uuid = uuid.uuid4().hex[:5]
    workplace_root = os.path.join(AGENT_VM_DIR, WORKPLACE_KIND, short_uuid)
    graph_dir = os.path.join(workplace_root, base)

    if os.path.exists(workplace_root):
        shutil.rmtree(workplace_root, ignore_errors=True)
    os.makedirs(workplace_root, exist_ok=True)

    if is_upgrade:
        source = os.path.join(GRAPHS_DIR, base)
        if not os.path.exists(os.path.join(source, "graph.json")):
            return f"❌ 无法执行升级：正式目录中未找到 '{base}/graph.json'。", ""
        ignore = shutil.ignore_patterns(
            "__pycache__", ".git", "node_modules", "evals", "*.pyc"
        )
        shutil.copytree(source, graph_dir, ignore=ignore)
        os.makedirs(os.path.join(graph_dir, "asset"), exist_ok=True)
        action_msg = f"已将现有的 '{base}/' 拷贝至进化沙盒进行升级"
    else:
        os.makedirs(os.path.join(graph_dir, "asset"), exist_ok=True)
        with open(
            os.path.join(graph_dir, "graph.json"), "w", encoding="utf-8", newline="\n"
        ) as f:
            json.dump(_skeleton(base, goal), f, ensure_ascii=False, indent=2)
        action_msg = f"已为你搭建了全新的 '{base}' 图骨架（含最小可用示例）"

    _write_sandbox(workplace_root, graph_dir, base, goal)

    sandbox_root = f"/agent_vm/{WORKPLACE_KIND}/{short_uuid}"
    return (
        f"【Graph 工厂分配成功】工作区路径：{sandbox_root}（workplace_id: {short_uuid}）。\n"
        f"{action_msg}。\n"
        f"💡 系统已在沙盒根目录生成官方说明文档 GUIDE.md（含节点类型词汇表/端口语义），动手前请先通读！\n"
        f"🧪 自测脚本：`{base}/evals/validate.py`，在沙盒根目录执行 "
        f"`uv run {base}/evals/validate.py` 即可完成格式 / 功能 / 关键词汇三重校验"
        f"（结论写入 {base}/evals/outputs/validation.json）。\n"
        f'🔀 校验全绿后，用 KernelUpgrade(action="merge", type="graph", target="{short_uuid}/{base}") 申请合并。'
    ), short_uuid


def _latest_validation_ok(workplace_root: str, name: str) -> tuple[bool, str]:
    """宿主侧重跑同一套校验（防篡改），返回 (是否通过, 结论文本)。"""
    folder = os.path.join(workplace_root, name)
    if not os.path.exists(os.path.join(folder, "graph.json")):
        return False, f"沙盒中未找到 '{name}/graph.json'"
    report = validate_graph_folder(folder, expected_name=name)
    return validation_summary(report)


def graph_request_handle(workplace_root: str, name: str, is_approved: bool) -> str:
    """处理 Graph 合并请求：宿主侧校验 + 拷贝正式 graph 目录 + Git 提交"""
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
            f"请在沙盒内执行 `uv run {base}/evals/validate.py` 修复全部 error 项后再申请合并。"
        )

    source_dir = os.path.join(workplace_root, base)
    target_dir = os.path.join(GRAPHS_DIR, base)
    is_upgrade = os.path.exists(target_dir)

    if is_upgrade:
        shutil.rmtree(target_dir, ignore_errors=True)
    os.makedirs(os.path.dirname(target_dir), exist_ok=True)
    ignore = shutil.ignore_patterns(
        "__pycache__", ".git", "node_modules", "evals", "*.pyc"
    )
    shutil.copytree(source_dir, target_dir, ignore=ignore)

    # Git 版本接管（首次自动 init）
    ensure_git_repo(GRAPHS_DIR, "__pycache__/\n*.pyc\n", create=True)
    commit_msg = (
        f"{'upgrade' if is_upgrade else 'add'} graph {base} "
        f"{datetime.now().strftime('%Y-%m-%d')}"
    )
    commit_paths(GRAPHS_DIR, [base], commit_msg)

    return (
        f"🎉 审批通过！Graph '{base}' 成功合并。\n"
        f"📁 正式路径: {target_dir}\n"
        f"🔍 校验: {verdict_text}\n"
        f"Git: {commit_msg}"
    )


__all__ = ["graph_factory_init", "graph_request_handle"]

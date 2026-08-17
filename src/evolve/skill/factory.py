"""
Skill 进化工厂核心逻辑 (evolve/skill/factory.py)
"""

import os
import shutil
import uuid
import subprocess
from datetime import datetime

from src.utils.config import SKILL_DIR, AGENT_VM_DIR

# 引入新的生成器
from .guide_generator import generate_skill_guide


def skill_improve_init(skill_name: str, is_upgrade: bool) -> tuple[str, str]:
    """初始化 Skill 进化沙盒，返回 (系统提示, workplace_id)"""
    short_uuid = uuid.uuid4().hex[:5]
    workplace_root = os.path.join(AGENT_VM_DIR, "skill_workplace", short_uuid)
    workplace_skill_dir = os.path.join(workplace_root, skill_name)

    if os.path.exists(workplace_root):
        shutil.rmtree(workplace_root, ignore_errors=True)
    os.makedirs(workplace_root, exist_ok=True)

    source_skill_dir = os.path.join(SKILL_DIR, skill_name)

    if is_upgrade:
        shutil.copytree(source_skill_dir, workplace_skill_dir)
        action_msg = f"已将现有的 '{skill_name}' 拷贝至进化沙盒进行升级"
    else:
        os.makedirs(workplace_skill_dir)
        for sub_dir in ["scripts", "references", "assets", "evals", "evals/files"]:
            os.makedirs(os.path.join(workplace_skill_dir, sub_dir), exist_ok=True)

        skill_md_content = f"---\nname: {skill_name}\ndescription: 请在此处填写对 {skill_name} 的描述信息（1-1024个字符）。必须使用祈使句（如：Use this skill when...）。\n---\n\n## 步骤说明\n\n在此处编写具体的任务执行指令...\n"
        with open(
            os.path.join(workplace_skill_dir, "SKILL.md"),
            "w",
            encoding="utf-8",
            newline="\n",
        ) as f:
            f.write(skill_md_content)

        evals_json_content = f"""{{
  "skill_name": "{skill_name}",
  "triggers": [
    {{
      "query": "在此输入正例：应唤醒本技能的真实用户请求（口语/缩写/复杂意图）",
      "should_trigger": true
    }},
    {{
      "query": "在此输入反例：包含技能关键词但实际不需要本技能处理的请求",
      "should_trigger": false
    }}
  ],
  "evals": [
    {{
      "id": "basic_test_1",
      "prompt": "在此处输入模拟用户的真实提问。必须自包含：从一开始就写明本次任务所需的全部信息，禁止任何需要用户中途输入或确认的交互；只用附件文件名，不要写绝对路径",
      "files": [
        "evals/files/示例附件.txt"
      ],
      "expected_output": "人类可读的预期结果描述",
      "assertions": [
        "输出的 JSON 文件格式必须合法",
        "不能在日志中打印敏感信息"
      ]
    }}
  ]
}}"""
        with open(
            os.path.join(workplace_skill_dir, "evals", "evals.json"),
            "w",
            encoding="utf-8",
            newline="\n",
        ) as f:
            f.write(evals_json_content)

        action_msg = f"已为你搭建了全新的 '{skill_name}' 骨架"

    # 生成忽略文件
    gitignore_path = os.path.join(workplace_skill_dir, ".gitignore")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(
                "# 忽略运行缓存和依赖\n__pycache__/\n*.py[cod]\nnode_modules/\n.venv/\nvenv/\n.env\n"
            )

    # 🌟 生成单文件官方指导手册
    with open(
        os.path.join(workplace_root, "GUIDE.md"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(generate_skill_guide(skill_name))

    # 🌟 精准的 API 返回引导：显式携带 workplace_id，路径使用沙盒视角的 /agent_vm 前缀
    sandbox_root = f"/agent_vm/skill_workplace/{short_uuid}"
    return (
        f"【技能工厂分配成功】工作区路径：{sandbox_root}（workplace_id: {short_uuid}）。\n"
        f"{action_msg}。\n"
        f"💡 提示：系统已在沙盒根目录为你生成了官方说明文档 GUIDE.md（覆盖创建/升级/盲测/提交全流程），动手前请先通读！"
        f"注意：盲测必须通过 Request(skill_test) 获得老板批准后由系统自动运行。"
    ), short_uuid


def skill_generate_diff(skill_name: str, workplace_root: str) -> str:
    source_dir = os.path.join(SKILL_DIR, skill_name)
    target_dir = os.path.join(workplace_root, skill_name)

    if not os.path.exists(source_dir):
        return f"这是一个全新的 Skill：{skill_name}，无历史版本（全部为新增）。"

    try:
        result = subprocess.run(
            ["git", "diff", "--no-index", source_dir, target_dir],
            capture_output=True,
            text=True,
        )
        diff_output = result.stdout
        if not diff_output.strip():
            return "文件内容与主库相比没有任何改变。"
        return diff_output
    except Exception as e:
        return f"差异对比生成失败: {str(e)}"


def skill_request_handle(
    workplace_root: str, skill_name: str, is_approved: bool
) -> str:
    # 修改点：如果拒绝，不删除工作区，保留给Agent继续修改
    if not is_approved:
        return (
            f"人类拒绝了 {skill_name} 的进化/合并请求，已保留当前工作区供你继续调整。"
        )

    source_dir = os.path.join(workplace_root, skill_name)
    target_dir = os.path.join(SKILL_DIR, skill_name)

    is_upgrade = os.path.exists(target_dir)

    # 核心修改：先彻底删除旧文件夹，再移动新的过去
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir, ignore_errors=True)
    os.makedirs(os.path.dirname(target_dir), exist_ok=True)
    shutil.copytree(source_dir, target_dir)

    skills_root = SKILL_DIR
    git_dir = os.path.join(skills_root, ".git")

    if not os.path.exists(git_dir):
        subprocess.run(["git", "init"], cwd=skills_root)

    gitignore_path = os.path.join(skills_root, ".gitignore")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write("*.pyc\n__pycache__/\n.DS_Store\n")

    subprocess.run(["git", "add", skill_name], cwd=skills_root)
    subprocess.run(["git", "add", ".gitignore"], cwd=skills_root)

    action = "upgrade" if is_upgrade else "add"
    current_date = datetime.now().strftime("%Y-%m-%d")
    commit_msg = f"{action} skill {skill_name} {current_date}"

    subprocess.run(["git", "commit", "-m", commit_msg], cwd=skills_root)

    return f"审批通过！已合并至正式区并触发 Git Commit: '{commit_msg}'"


def skill_rollback(skill_name: str) -> str:
    """
    将指定的 Skill 强制回滚到上一次修改的 Git 提交版本。
    """
    skills_root = SKILL_DIR
    git_dir = os.path.join(skills_root, ".git")

    if not os.path.exists(git_dir):
        return "回滚失败：没有找到 Git 仓库，无法追溯历史。"

    try:
        # 检查这个 skill 是否有提交历史
        log_check = subprocess.run(
            ["git", "log", "--oneline", "--", skill_name],
            cwd=skills_root,
            capture_output=True,
            text=True,
        )
        if not log_check.stdout.strip():
            return f"回滚失败：未找到 '{skill_name}' 的任何 Git 提交历史。"

        # 从上一个版本 (HEAD~1) 检出该目录的文件覆盖当前目录
        subprocess.run(
            ["git", "checkout", "HEAD~1", "--", skill_name],
            cwd=skills_root,
            check=True,
            capture_output=True,
        )

        # 提交回滚记录
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_msg = f"rollback skill {skill_name} to previous state at {current_date}"

        subprocess.run(["git", "commit", "-m", commit_msg], cwd=skills_root, check=True)

        return (
            f"回滚成功！'{skill_name}' 已恢复至上一个版本，并生成了 Rollback Commit。"
        )

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8") if e.stderr else str(e)
        return f"回滚执行异常：{stderr}"

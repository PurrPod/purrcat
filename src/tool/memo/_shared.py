"""Memo 的纯文案与 Markdown 段落拼装。

文件读写与 Agent 调用留在 memo_operations；这里只处理可单测的字符串逻辑。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date_format(date_str: str) -> bool:
    """验证日期格式 YYYY-MM-DD 且为真实日期。"""
    if not _DATE_RE.match(date_str or ""):
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def build_memory_update_prompts(
    current_md: str, work_exp: list, user_profile: list
) -> tuple[str, str]:
    """构造 MEMORY.md 智能整理所需的 system / user 提示词。"""
    system_prompt = (
        "你是一个极其克制且追求高效的后台记忆整理 Agent。\n"
        "\n"
        "当前有两个存储层：\n"
        "- 记忆数据库（事无巨细的全量日志，长期保留，不用你管）\n"
        '- MEMORY.md（注入工作主 Agent 系统提示词的"浅层意识缓存"，只保留最通用、最高频的核心经验）\n'
        "\n"
        "你的任务：根据最新传入的工作经验和用户画像，智能更新 MEMORY.md。\n"
        "\n"
        "【定位铁律】\n"
        "MEMORY.md 是主 Agent 在每一步决策时都会扫一眼的东西。它必须极度精炼、极度通用、没有一丝水分。\n"
        "任何只对某个特定项目、某次特定运行有意义的细节，都不配进入这个文件。\n"
        "每条经验必须能用一句话说清：什么情况下，应该立刻采取什么行动或想起什么规则。不超过 80 字。\n"
        "\n"
        "【通用性判别标准】\n"
        "以下内容 **绝对不得收录**：\n"
        "- 特定文件路径、IP地址、版本号\n"
        '- 单次运行结果（如"某次测试通过率 97%"）\n'
        "- 仅适用于某个特定项目、特定目录结构的操作步骤\n"
        "\n"
        "以下内容 **优先收录**：\n"
        '- 跨项目反复出现的方法论（如"三层解耦架构"）\n'
        '- 反直觉的系统行为（如"bash cp 无法跨环境到宿主机路径"）\n'
        "- 曾被重复踩过的坑（同一类问题出现 2 次以上，说明有长期价值）\n"
        "- 用户不可触碰的红线或隐性期待\n"
        "\n"
        "【数量与淘汰规则】\n"
        "- MEMORY.md 中经验总数 **必须 ≤ 15 条**\n"
        "- 每新增 1 条经验，必须从现有经验中淘汰至少 1 条（直接从文档中移除，不留删除线或批注）\n"
        "- 淘汰时，优先移除：① 最久未更新的经验 ② 适用场景最窄的经验 ③ 与其他经验重叠度最高的经验\n"
        "- 同类经验必须合并为一条，禁止出现两条指向同一场景的独立条目\n"
        "\n"
        "【写入方式】\n"
        "你必须调用 overwrite_memory_md 工具，用整理后的全量内容（≤15 条）完整覆写 MEMORY.md。"
    )
    user_prompt = (
        f"【现有长期记忆档案】\n{current_md if current_md else '（暂无）'}\n\n"
        f"【本次新增工作经验】\n{work_exp if work_exp else '（无）'}\n\n"
        f"【本次新增用户画像】\n{user_profile if user_profile else '（无）'}"
    )
    return system_prompt, user_prompt


def extract_overwrite_content(arguments: str) -> str:
    """从 overwrite_memory_md 的工具参数里取出全量 Markdown。"""
    return json.loads(arguments).get("new_markdown_content", "")


def format_cached_memo(memo_list: Any) -> str:
    """无查询参数时返回的缓存记忆文本。"""
    if not memo_list:
        return "当前无缓存记忆"
    import yaml

    return yaml.dump(memo_list, allow_unicode=True)


def format_search_results(result: Any) -> str:
    """把检索返回值统一成带序号与相似度的文本。"""
    if isinstance(result, str):
        return result or "未检索到相关记忆。"

    res_str = ""
    for idx, item in enumerate(result or []):
        if isinstance(item, dict):
            res_str += (
                f"[{idx + 1}] {item.get('date', '')} - "
                f"相似度: {item.get('score', 0)}\n内容: {item.get('content', '')}\n\n"
            )
    return res_str or "未检索到相关记忆。"

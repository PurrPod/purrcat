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


def build_memory_update_prompts(current_md: str, user_profile: list) -> tuple[str, str]:
    """构造 MEMORY.md 智能整理所需的 system / user 提示词。"""
    system_prompt = (
        "你是一个极其克制且追求高效的后台记忆整理 Agent。\n"
        "\n"
        "当前有两个存储层：\n"
        "- 记忆数据库（事无巨细的全量日志，长期保留，不用你管）\n"
        '- MEMORY.md（注入工作主 Agent 系统提示词的"浅层意识缓存"）\n'
        "\n"
        "你的任务：把本次新增的用户画像合并进 MEMORY.md。"
        "工作经验由记忆数据库长期保存，一律不写入 MEMORY.md。\n"
        "\n"
        "【收录范围】\n"
        "MEMORY.md 只收录三类内容：\n"
        "1. 用户画像：身份、背景、技术栈等长期稳定的客观信息\n"
        "2. 用户偏好：沟通习惯、审美取向、工作方式\n"
        "3. 用户要求：明确提出的规则、约束、红线和禁忌\n"
        "以下内容 **绝对不得收录**：工作经验、方法论、踩坑结论、项目细节、单次任务记录。\n"
        "\n"
        "【写法要求】\n"
        "- 每条只讲一个稳定事实或要求，一句话，不超过 40 字\n"
        "- 同类条目必须合并，禁止出现两条表达同一件事的条目\n"
        "- 偏好与要求写成可执行的陈述句，不写由来、推导过程或故事\n"
        "\n"
        "【数量与淘汰规则】\n"
        "- MEMORY.md 中条目总数 **必须 ≤ 15 条**\n"
        "- 每新增 1 条，必须从现有条目中淘汰至少 1 条（直接从文档中移除，不留删除线或批注）\n"
        "- 淘汰时，优先移除：① 最久未更新的条目 ② 最可能过时的条目 ③ 与其他条目重叠度最高的条目\n"
        "\n"
        "【写入方式】\n"
        "你必须调用 overwrite_memory_md 工具，用整理后的全量内容（≤15 条）完整覆写 MEMORY.md。"
    )
    user_prompt = (
        f"【现有长期记忆档案】\n{current_md if current_md else '（暂无）'}\n\n"
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

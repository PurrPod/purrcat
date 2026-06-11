from typing import Any, Dict
from src.harness.node.base import BaseNode
from src.tool.search.skill_search import SkillSearcher


class Node(BaseNode):
    """Skill Info 节点：输出指定的 Skill 列表及其描述提示词"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "🛠️ [Skill Info] 正在获取技能信息...")

        # 获取面板中配置的技能名列表
        skills_config = self.config.get("skills_list", [])
        requested_names = [
            item.get("name")
            for item in skills_config
            if isinstance(item, dict) and item.get("name")
        ]

        if not requested_names:
            self.log(context, "WARNING", "⚠️ [Skill Info] 未配置任何技能名称，输出为空")
            return {"skill_kit_string": ""}

        # 调用底层接口获取所有技能
        searcher = SkillSearcher()
        all_skills = {
            s.get("name"): s.get("description", "No description available.")
            for s in searcher.skills
        }

        result_lines = [
            "[Skill Kit:These are the recommended skill, You can fetch these skill to finish the task more efficiently]"
        ]

        found_count = 0
        for name in requested_names:
            desc = all_skills.get(name, "未找到该技能描述")
            result_lines.append(f"- {name}: {desc}")
            if name in all_skills:
                found_count += 1

        skill_kit_str = "\n".join(result_lines)

        self.log(
            context,
            "SYSTEM",
            f"✅ [Skill Info] 成功打包 {found_count} 个技能的提示词。",
        )

        return {"skill_kit_string": skill_kit_str}

import asyncio
from pathlib import Path
from typing import Dict, Any
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """技能获取节点：独立负责搜索和读取本地技能库文件"""

    async def execute(
        self, inputs: Dict[str, Any], force_push_msgs: list, context: Any
    ) -> Dict[str, Any]:
        skill_name = inputs.get("skill_name") or self.config.get("skill_name", "")

        skill_content = await asyncio.to_thread(self._fetch_skill_local, skill_name)
        return {"skill_content": skill_content}

    def _fetch_skill_local(self, skill_name: str) -> str:
        from src.utils.config import SKILL_DIR

        base_dir = Path(SKILL_DIR)
        target_dir = base_dir / skill_name
        md_file = target_dir / "SKILL.md"
        content = ""
        found_name = skill_name

        if not md_file.exists():
            for item in base_dir.iterdir():
                if item.is_dir():
                    dir_md = item / "SKILL.md"
                    if dir_md.exists():
                        with open(dir_md, "r", encoding="utf-8") as f:
                            text = f.read()
                        if text.startswith("---"):
                            parts = text.split("---", 2)
                            if len(parts) >= 3:
                                frontmatter_str = parts[1]
                                for line in frontmatter_str.split("\n"):
                                    line = line.strip()
                                    if line and ":" in line:
                                        key, value = line.split(":", 1)
                                        if (
                                            key.strip() == "name"
                                            and value.strip() == skill_name
                                        ):
                                            content = parts[2].strip()
                                            found_name = skill_name
                                            target_dir = item
                                            break

        if not content and md_file.exists():
            with open(md_file, "r", encoding="utf-8") as f:
                text = f.read()
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    content = parts[2].strip()
            else:
                content = text

        if not content:
            return ""

        skill_path = f"/agent_vm/skill/{target_dir.name}"
        return f"""相关技能：{found_name}
技能目录：{skill_path}
请结合技能手册进行任务：
{content}"""

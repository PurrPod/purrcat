from typing import Any, Dict
import json

from jinja2 import Template

from src.harness.node.base import BaseNode


class Node(BaseNode):
    """动态模板渲染器：接收模板和动态变量，直接输出拼接渲染后的文本"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "📝 [模板渲染] 开始执行")

        template_str = inputs.get("template") or self.config.get("template", "")

        if not template_str:
            self.log(context, "WARNING", "⚠️ [模板渲染] 模板为空，将输出空字符串。")
            return {"rendered_text": ""}

        variables = {k: v for k, v in inputs.items() if k != "template"}

        self.log(
            context,
            "SYSTEM",
            f"🔑 [模板渲染] 注入变量:\n{json.dumps(variables, indent=2, ensure_ascii=False)}",
        )

        try:
            rendered_content = Template(template_str).render(**variables)

            output_preview = (
                rendered_content[:1000] + "..."
                if len(rendered_content) > 1000
                else rendered_content
            )
            self.log(context, "SYSTEM", f"📤 [渲染结果]:\n{output_preview}")

            return {"rendered_text": rendered_content}

        except Exception as e:
            self.log(context, "ERROR", f"❌ [模板渲染报错] 变量注入失败: {e}")
            raise ValueError(f"模板渲染失败，请检查变量名是否匹配: {e}")

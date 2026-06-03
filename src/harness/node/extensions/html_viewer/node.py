from typing import Any, Dict
from src.harness.node.base import BaseNode
from src.harness.enums import LogType
import markdown


class Node(BaseNode):
    """HTML 看板：将纯文本/Markdown 渲染为带样式的 HTML 页面"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "📊 [HTML看板] 正在生成视图...")

        content = inputs.get("content", "")
        title = self.config.get("title", "Data Dashboard")

        try:
            html_content = markdown.markdown(
                str(content), extensions=["tables", "fenced_code"]
            )
        except Exception:
            html_content = f"<pre>{content}</pre>"

        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 2rem; background: #fdfaf5; }}
        h1 {{ border-bottom: 2px solid #D47A5A; padding-bottom: 0.5rem; color: #1a1a1a; }}
        pre {{ background: #1a1a1a; color: #fdfaf5; padding: 1rem; border-radius: 8px; overflow-x: auto; }}
        code {{ background: #e9ecef; padding: 0.2rem 0.4rem; border-radius: 4px; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="content">
        {html_content}
    </div>
</body>
</html>"""

        self.log(context, LogType.ARTIFACT, full_html)
        self.log(context, "SYSTEM", "✅ [HTML看板] 已成功向前端推送可视化视图！")
        return {"html_source": full_html}

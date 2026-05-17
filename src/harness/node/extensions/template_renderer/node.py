from typing import Any, Dict
from jinja2 import Template
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """动态模板渲染器：接收模板和动态变量，直接输出拼接渲染后的文本"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "=" * 50)
        self.log(context, "SYSTEM", "📝 [模板渲染] 节点启动")
        self.log(context, "SYSTEM", f"📥 [模板渲染] 收到输入包裹: {list(inputs.keys()) if inputs else '空'}")

        template_str = inputs.get("template") or self.config.get("template", "")
        
        if not template_str:
            self.log(context, "WARNING", "⚠️ [模板渲染] 模板为空，将输出空字符串。")
            return {"rendered_text": ""}

        template_preview = template_str[:150] + "..." if len(template_str) > 150 else template_str
        self.log(context, "SYSTEM", f"📄 [模板内容] {template_preview}")

        variables = {k: v for k, v in inputs.items() if k != "template"}

        self.log(context, "SYSTEM", f"🔑 [变量注入] 共 {len(variables)} 个变量: {list(variables.keys())}")
        for var_name, var_val in variables.items():
            val_preview = str(var_val)[:80] + "..." if len(str(var_val)) > 80 else str(var_val)
            self.log(context, "SYSTEM", f"  🔹 {var_name} = {val_preview}")

        try:
            rendered_content = Template(template_str).render(**variables)
            
            self.log(context, "SYSTEM", f"✅ [模板渲染] 渲染成功，输出长度: {len(rendered_content)}")
            output_preview = rendered_content[:200] + "..." if len(rendered_content) > 200 else rendered_content
            self.log(context, "SYSTEM", f"📤 [渲染结果] {output_preview}")
            
            return {"rendered_text": rendered_content}
            
        except Exception as e:
            self.log(context, "ERROR", f"❌ [模板渲染报错] 变量注入失败: {e}")
            raise ValueError(f"模板渲染失败，请检查变量名是否匹配: {e}")

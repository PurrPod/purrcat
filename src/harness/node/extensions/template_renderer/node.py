from typing import Any, Dict
from jinja2 import Template
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """动态模板渲染器：接收模板和动态变量，直接输出拼接渲染后的文本"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        # 1. 提取模板字符串（优先从连线输入取，否则从配置框取）
        template_str = inputs.get("template") or self.config.get("template", "")
        
        if not template_str:
            self.log(context, "WARNING", "⚠️ [模板渲染] 模板为空，将输出空字符串。")
            return {"rendered_text": ""}

        # 2. 核心魔法：将 inputs 中除了 'template' 以外的所有键值对，都视为要注入的变量！
        # 这样无论前端动态生成了多少个引脚连线传过来，都能自动识别。
        variables = {k: v for k, v in inputs.items() if k != "template"}

        self.log(context, "SYSTEM", f"⚡ [模板渲染] 正在注入 {len(variables)} 个变量: {list(variables.keys())}")

        try:
            # 3. 进行 Jinja2 渲染
            rendered_content = Template(template_str).render(**variables)
            
            self.log(context, "SYSTEM", f"✅ [模板渲染] 渲染成功，输出长度: {len(rendered_content)}")
            
            outputs = {"rendered_text": rendered_content}
            self.save_checkpoints(context, {"inputs": inputs, "outputs": outputs})
            return outputs
            
        except Exception as e:
            self.log(context, "ERROR", f"❌ [模板渲染报错] 变量注入失败: {e}")
            raise ValueError(f"模板渲染失败，请检查变量名是否匹配: {e}")

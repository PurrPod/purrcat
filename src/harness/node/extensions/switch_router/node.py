from typing import Any, Dict
from src.harness.node.base import BaseNode

class Node(BaseNode):
    """精准分流器：比较 match_value 是否等于配置的 cases 中的 value"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        match_value = str(inputs.get("match_value", "")).strip()
        cases = self.config.get("cases", [])
        
        self.log(context, "SYSTEM", f"🔀 [分流器] 收到判断值: '{match_value}'")

        for case in cases:
            if not isinstance(case, dict):
                continue
            case_name = case.get("name")
            case_value = str(case.get("value", "")).strip()
            
            if not case_name:
                continue
                
            if match_value == case_value:
                self.log(context, "SYSTEM", f"✅ [分流器] 匹配成功！值 '{match_value}' 命中分支: [{case_name}]")
                return {case_name: inputs.get("match_value")}

        self.log(context, "SYSTEM", "⚠️ [分流器] 无匹配项，走 default 兜底分支。")
        return {"default": inputs.get("match_value")}
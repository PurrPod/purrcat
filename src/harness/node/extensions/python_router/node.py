import traceback
from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """代码级条件路由：执行自定义 Python 代码片段，按分支分发数据"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        code_str = inputs.get("code") or self.config.get("code", "")

        if not code_str:
            self.log(context, "WARNING", "⚠️ [代码路由] 未配置代码，将默认走 'default' 分支。")
            return {"selected_branch": "default", "default": inputs}

        local_scope = {}

        try:
            self.log(context, "SYSTEM", f"⚡ [代码路由] 正在动态编译并执行分支代码...")

            exec(code_str, {}, local_scope)

            if "evaluate" not in local_scope:
                raise ValueError("代码中找不到名为 'evaluate(inputs)' 的函数入口！")

            evaluate_func = local_scope["evaluate"]

            selected_branch = evaluate_func(inputs)

            if not isinstance(selected_branch, str):
                self.log(context, "WARNING", f"⚠️ [代码路由] evaluate 返回值非字符串(类型为 {type(selected_branch)})，尝试强制转换。")
                selected_branch = str(selected_branch)

            self.log(context, "SYSTEM", f"✅ [代码路由] 判定完成！命中分支: {selected_branch}")

            outputs = {
                "selected_branch": selected_branch,
                selected_branch: inputs
            }

            return outputs

        except Exception as e:
            error_detail = traceback.format_exc()
            self.log(context, "ERROR", f"❌ [代码路由崩溃] 执行异常:\n{error_detail}")
            raise RuntimeError(f"条件代码执行失败: {str(e)}")

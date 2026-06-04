import re
from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        var_a = inputs.get("var_a")
        operator = self.config.get("operator", "==")

        # 核心：优先取连线数据，没有连线再取配置数据
        if "var_b" in inputs and inputs["var_b"] is not None:
            var_b = inputs["var_b"]
            source_b = "连线"
        else:
            var_b = self.config.get("var_b", "")
            source_b = "面板"

        self.log(
            context,
            "SYSTEM",
            f"⚖️ [条件判断] var_a='{var_a}', op='{operator}', var_b='{var_b}' (来源:{source_b})",
        )

        is_true = False

        if operator == "is_empty":
            is_true = (
                var_a is None or str(var_a).strip() == "" or var_a == [] or var_a == {}
            )
        elif operator == "not_empty":
            is_true = (
                var_a is not None
                and str(var_a).strip() != ""
                and var_a != []
                and var_a != {}
            )
        else:
            str_a = str(var_a) if var_a is not None else ""
            str_b = str(var_b)

            try:
                is_num = False
                num_a, num_b = 0.0, 0.0
                try:
                    num_a = float(str_a)
                    num_b = float(str_b)
                    is_num = True
                except ValueError:
                    pass

                if operator == "==":
                    is_true = (num_a == num_b) if is_num else (str_a == str_b)
                elif operator == "!=":
                    is_true = (num_a != num_b) if is_num else (str_a != str_b)
                elif operator == ">":
                    is_true = (num_a > num_b) if is_num else (str_a > str_b)
                elif operator == ">=":
                    is_true = (num_a >= num_b) if is_num else (str_a >= str_b)
                elif operator == "<":
                    is_true = (num_a < num_b) if is_num else (str_a < str_b)
                elif operator == "<=":
                    is_true = (num_a <= num_b) if is_num else (str_a <= str_b)
                elif operator == "contains":
                    is_true = str_b in str_a
                elif operator == "not_contains":
                    is_true = str_b not in str_a
                elif operator == "startswith":
                    is_true = str_a.startswith(str_b)
                elif operator == "endswith":
                    is_true = str_a.endswith(str_b)
                elif operator == "regex_match":
                    is_true = bool(re.search(str_b, str_a))
            except Exception as e:
                self.log(context, "ERROR", f"❌ 条件比较时发生错误: {e}")
                is_true = False

        if is_true:
            self.log(context, "SYSTEM", "✅ [条件判断] 结果为 True，执行 [True] 分支。")
            return {"True": var_a}
        else:
            self.log(context, "SYSTEM", "❌ [条件判断] 结果为 False，执行 [False] 分支。")
            return {"False": var_a}

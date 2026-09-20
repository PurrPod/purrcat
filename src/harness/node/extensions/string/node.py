import json

from typing import Any, Dict

from src.harness.node.base import BaseNode


class Node(BaseNode):
    """自定义输入节点：用户直接写内容，按内容推导出多数据类型的输出端口。

    提供一个输入区域供填写任意内容，同一份内容按可解析程度派生出
    字符串 / 数字 / 布尔 / JSON 四种类型的输出端口，下游按需取用。
    """

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        raw = self.config.get("value", "")
        if not isinstance(raw, str):
            raw = str(raw)
        text = raw.strip()

        self.log(
            context,
            "SYSTEM",
            f"📝 [自定义输入] 输出 {len(text)} 字符: {text[:60]}{'...' if len(text) > 60 else ''}",
        )

        # 字符串：原文（保留兼容别名，先前 string 节点的输出端口名即 text）
        out_text = self.pack(text, "string", "text/plain")

        # 数字：可解析为整数/浮点才输出，否则无值（None）
        number = None
        try:
            num = json.loads(text)
            if isinstance(num, bool):
                raise ValueError
            if isinstance(num, (int, float)):
                number = num
            else:
                # 兼容 "3.14" "1_000" 等带单位的非 JSON 数值文本
                fnum = float(text.replace(",", "").replace("_", ""))
                number = int(fnum) if fnum.is_integer() else fnum
        except Exception:
            number = None
        out_number = self.pack(number, "number", "application/json")

        # 布尔：true/false/1/0（大小写无关）
        low = text.lower()
        if low in ("true", "1", "yes", "是"):
            out_bool = self.pack(True, "boolean", "application/json")
        elif low in ("false", "0", "no", "否"):
            out_bool = self.pack(False, "boolean", "application/json")
        else:
            out_bool = self.pack(None, "boolean", "application/json")

        # JSON：整体可解析为对象/数组才输出 jsonstring，否则无值
        out_json = None
        try:
            parsed = json.loads(text)
            if isinstance(parsed, (dict, list)):
                out_json = self.pack(
                    json.dumps(parsed, ensure_ascii=False),
                    "jsonstring",
                    "application/json",
                )
            else:
                out_json = self.pack(None, "jsonstring", "application/json")
        except Exception:
            out_json = self.pack(None, "jsonstring", "application/json")

        return {
            "text": out_text,
            "number": out_number,
            "boolean": out_bool,
            "json": out_json,
        }

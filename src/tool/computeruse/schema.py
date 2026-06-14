"""ComputerUse 工具大模型输入结构"""

COMPUTERUSE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ComputerUse",
        "description": "跨平台计算机物理控制工具。允许你像人类一样查看屏幕、移动鼠标、点击和打字。\n调用截图 (screenshot) 时，会自动进行 OCR 与 UI Tree 融合，并在图上打上 [ID] 标签，你可以直接通过 element_id 来交互，彻底告别坐标计算！",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "要执行的物理动作",
                    "enum": [
                        "screenshot",
                        "find_element",
                        "mouse_move",
                        "left_click",
                        "right_click",
                        "middle_click",
                        "double_click",
                        "left_click_drag",
                        "scroll",
                        "type",
                        "key",
                        "hide_other_apps"
                    ],
                },
                "coordinate": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "目标 x, y 坐标，例如 [100, 200]。",
                },
                "element_id": {
                    "type": "string",
                    "description": "首选交互方式！截图中带有数字标签的元素 ID（如 '12'），直接传入 ID 即可精准点击，无需传 coordinate！",
                },
                "text": {
                    "type": "string",
                    "description": "要输入的文本(type必填)，快捷键(key必填)，或要查找的元素名称(find_element必填)",
                },
                "scroll_amount": {
                    "type": "integer",
                    "description": "scroll 动作必填。滚动量，正数代表向下滚，负数代表向上滚（如 500 或 -500）",
                },
                "wait_time": {
                    "type": "number",
                    "description": "可选。操作完成后的隐式等待时间（秒），用于等动画加载（如 1.5），默认 0.1",
                },
                "keep_apps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "hide_other_apps 的白名单",
                }
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}
"""ComputerUse 工具大模型输入结构"""

COMPUTERUSE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ComputerUse",
        "description": (
            "跨平台计算机物理控制工具。允许你像人类一样查看屏幕、移动鼠标、点击和打字。\n"
            "💡 核心工作流：\n"
            "1. 先调用 `screenshot` 获取带有 [ID] 标签的屏幕截图。\n"
            "2. 优先通过传入 `element_id` 来进行点击或输入操作"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": (
                        "要执行的具体动作。各动作的必填参数说明：\n"
                        "- screenshot: 截取屏幕并返回带 ID 标签的UI元素。这是所有交互的基础。\n"
                        "- find_element: 需配合 `text` 参数搜索屏幕上的指定元素。\n"
                        "- left_click/right_click/double_click: 需配合 `element_id` (优先) 或 `coordinate`。\n"
                        "- left_click_drag: 拖拽，建议传入包含4个值的 `coordinate` [起点x, 起点y, 终点x, 终点y]。\n"
                        "- scroll: 滚动屏幕，需配合 `scroll_amount` 参数。\n"
                        "- type: 模拟键盘输入，需配合 `text` 参数。\n"
                        "- key: 触发系统快捷键，需配合 `text` 参数。\n"
                        "- launch_app: 启动应用或使用浏览器打开某个url，需配合 `text` 参数。\n"
                        "- list_app: 列出本地配置的可用应用白名单。\n"
                        "- hide_other_apps: 隐藏/最小化无关窗口，可配合 `keep_apps`。"
                    ),
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
                        "hide_other_apps",
                        "launch_app",
                        "list_app",
                    ],
                },
                "coordinate": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "目标 x, y 坐标，例如 [100, 200]。如果是 left_click_drag (拖拽) 操作，建议传入4个值代表[起点x, 起点y, 终点x, 终点y]，例如 [100, 200, 300, 400] 以实现精准拖拽。",
                },
                "element_id": {
                    "type": "string",
                    "description": "首选交互方式！截图中带有数字标签的元素 ID（如 '12'），直接传入 ID 即可精准交互，无需传 coordinate！",
                },
                "text": {
                    "type": "string",
                    "description": (
                        "多用途文本参数，根据 action 的不同而变化：\n"
                        "1. type: 要输入的具体文字内容。\n"
                        "2. key: 快捷键组合（如 'ctrl+c', 'enter', 'win+d'）。\n"
                        "3. find_element: 要在屏幕上查找的元素文本内容。\n"
                        "4. launch_app: 既可以传入白名单中的应用名（如 '微信'），也可以直接传入完整的网址URL（如 'https://github.com'）以调用默认浏览器打开。"
                    ),
                },
                "scroll_amount": {
                    "type": "integer",
                    "description": "scroll 动作必填。滚动量，正数代表向下滚，负数代表向上滚（如 500 或 -500）。",
                },
                "wait_time": {
                    "type": "number",
                    "description": "可选。操作完成后的隐式等待时间（秒），用于等待系统动画或网络加载（如 1.5 或 3.0），默认 0.1秒。",
                },
                "keep_apps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "hide_other_apps 操作的白名单（包含不希望被最小化的应用名称列表）。",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}
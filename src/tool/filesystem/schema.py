FILESYSTEM_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "FileSystem",
        "description": "文件系统操作工具，支持导入(import)、导出(export)、列出目录(list)、以及读取分析图片(read_picture)四种操作",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型，必须为 import（导入）、export（导出）、list（列出目录）或 read_picture（读取图片进行大模型分析）",
                    "enum": ["import", "export", "list", "read_picture"],
                },
                "path_from": {
                    "type": "string",
                    "description": "源路径。import: 宿主机路径；export: 沙盒路径（必须以 /agent_vm/ 开头）；list: 要列出的目录（可选）；read_picture: 单张图片路径（也可使用 paths 参数代替）",
                },
                "path_to": {
                    "type": "string",
                    "description": "目标路径。import: 沙盒内目录（可选）；export: 宿主机路径（必填）；list/read_picture: 不支持此参数",
                },
                "depth": {
                    "type": "integer",
                    "description": "list 操作时的递归深度",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 5,
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": "list 操作时是否显示隐藏文件/目录",
                    "default": False,
                },
                "paths": {
                    "type": ["string", "array"],
                    "items": {
                        "type": "string"
                    },
                    "description": "仅在 read_picture 时使用。单个图片的绝对路径字符串，或多个图片路径组成的列表。请传入本地路径，如果是沙盒内图片，可以转换为本地文件路径，比如将/agent_vm改为./agent_vm"
                },
                "prompt": {
                    "type": "string",
                    "description": "仅在 read_picture 时使用。要求视觉大模型执行的指令提示词，例如 '请将图片中的表格转换为 markdown 格式'。"
                }
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}

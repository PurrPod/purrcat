FILESYSTEM_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "FileSystem",
        "description": "文件系统操作工具，支持导入、导出、列出目录三种操作",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型，必须为 import（导入）、export（导出）或 list（列出）",
                    "enum": ["import", "export", "list"]
                },
                "path_from": {
                    "type": "string",
                    "description": "源路径。import: 宿主机路径；export: 沙盒路径（必须以 /agent_vm/ 开头）；list: 要列出的目录（可选，默认当前目录）"
                },
                "path_to": {
                    "type": "string",
                    "description": "目标路径。import: 沙盒内目录（可选，默认 imports）；export: 宿主机路径（必填）；list: 不支持此参数"
                },
                "depth": {
                    "type": "integer",
                    "description": "list 操作时的递归深度，1=仅当前目录，2=包含子目录，以此类推",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 5
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": "list 操作时是否显示隐藏文件/目录",
                    "default": False
                }
            },
            "required": ["action"],
            "additionalProperties": False
        }
    }
}
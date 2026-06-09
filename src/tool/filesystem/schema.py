FILESYSTEM_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "FileSystem",
        "description": (
            "高级文件系统操作工具。\n"
            "支持目录浏览(list)、视觉分析(read_picture)、文件移动/重命名/导入导出(move)。\n"
            "强大的代码操作能力：读取(read)、编辑(edit)、复写(write)、文本搜索(search)与文件模式匹配(glob)。\n"
            "【特殊能力】：Read 操作内置了 MarkItDown，你可以直接使用 read 操作读取 .pdf, .docx, .xlsx, .pptx 等富文本和表格文件，它们会被自动解析为 Markdown 文本返回！"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型。枚举值：list, read_picture, read, edit, write, search, glob, move",
                    "enum": ["list", "read_picture", "read", "edit", "write", "search", "glob", "move"],
                },
                "path": {
                    "type": "string",
                    "description": "通用目标文件或目录路径。支持两种格式：\n1. 沙盒路径（以 /agent_vm/ 开头）\n2. 宿主机本地绝对/相对路径。\n适用于 list, read, edit, write, search, glob, move 等绝大多数操作。",
                },
                "picture_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "仅 read_picture 使用。多张图片路径数组，用于多图联合视觉分析。同样支持沙盒与本地路径映射。",
                },
                "destination": {
                    "type": "string",
                    "description": "仅 move 操作使用。移动或重命名的目标路径（同样支持沙盒路径与本地路径）。",
                },
                "offset": {
                    "type": "integer",
                    "description": "仅 read 使用。起始读取的行号，用于超大文件的分页。默认 0。",
                },
                "limit": {
                    "type": "integer",
                    "description": "仅 read 使用。最大读取行数，默认 2000 行。",
                },
                "old_string": {
                    "type": "string",
                    "description": "仅 edit 使用。要替换的旧文本（须包含足够上下文以确保唯一）。",
                },
                "new_string": {
                    "type": "string",
                    "description": "仅 edit 使用。要替换成的新文本。",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "仅 edit 使用。是否替换所有匹配项，默认 False。",
                    "default": False,
                },
                "content": {
                    "type": "string",
                    "description": "仅 write 使用。用于创建新文件或完全覆盖写入的完整内容。",
                },
                "pattern": {
                    "type": "string",
                    "description": "仅 search/glob 使用。search 传入正则，glob 传入通配符。",
                },
                "depth": {
                    "type": "integer",
                    "description": "仅 list 使用。目录递归深度，默认 1。",
                },
                "prompt": {
                    "type": "string",
                    "description": "仅 read_picture 使用。视觉大模型的提示词指令。",
                }
            },
            "required": ["action"],
            "additionalProperties": True,
        },
    },
}
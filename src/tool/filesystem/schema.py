FILESYSTEM_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "FileSystem",
        "description": (
            "高级文件系统操作工具。\n"
            "支持目录浏览(list)、文件传导(import/export)、视觉分析(read_picture)、文件移动/重命名(move)。\n"
            "强大的代码操作能力：读取(read)、编辑(edit)、复写(write)、文本搜索(search)与文件模式匹配(glob)。\n"
            "【特殊能力】：Read 操作内置了 MarkItDown，你可以直接使用 read 操作读取 .pdf, .docx, .xlsx, .pptx 等富文本和表格文件，它们会被自动解析为 Markdown 文本返回！"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型。枚举值：import, export, list, read_picture, read, edit, write, search, glob, move",
                    "enum": [
                        "import",
                        "export",
                        "list",
                        "read_picture",
                        "read",
                        "edit",
                        "write",
                        "search",
                        "glob",
                        "move",
                    ],
                },
                "path_from": {
                    "type": "string",
                    "description": "源文件或目录路径。支持 /agent_vm/ 开头的沙盒路径，会自动映射到正确的绝对路径。",
                },
                "path_to": {
                    "type": "string",
                    "description": "目标路径 (仅限 import/export/move 操作)。",
                },
                "path": {
                    "type": "string",
                    "description": "通用路径参数，作为 path_from 的替代方案使用。",
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
                    "description": "仅 edit 使用。⚠️注意: 必须包含足够上下文(通常2-4行相邻代码)以确保唯一！严禁包含 '123 | ' 行号前缀。⛔ 绝对禁止对由富文本(PDF/Word等)转码而来的 Markdown 文件使用 edit 操作！",
                },
                "new_string": {
                    "type": "string",
                    "description": "仅 edit 使用。要替换成的新文本。",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "仅 edit 使用。如果 old_string 在文件中多次出现（例如重命名某个变量），将此项设为 true 以替换全部。",
                    "default": False,
                },
                "content": {
                    "type": "string",
                    "description": "仅 write 使用。用于创建新文件或完全重写小文件的完整内容。⚠️警告: 如果是修改已有文件，请优先使用 Edit 工具而不是 Write 工具！",
                },
                "pattern": {
                    "type": "string",
                    "description": "仅 search/glob 使用。search 操作传入 Regex 正则(如 'function\\s+\\w+')；glob 操作传入通配符模式(如 '**/*.js' 寻找所有js文件)。",
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
                    "items": {"type": "string"},
                    "description": "仅在 read_picture 时使用。单个图片的绝对路径字符串，或多个图片路径组成的列表。请传入本地路径，如果是沙盒内图片，可以转换为本地文件路径，比如将/agent_vm改为./agent_vm",
                },
                "prompt": {
                    "type": "string",
                    "description": "仅在 read_picture 时使用。要求视觉大模型执行的指令提示词，例如 '请将图片中的表格转换为 markdown 格式'。",
                },
            },
            "required": ["action"],
            "additionalProperties": True,
        },
    },
}

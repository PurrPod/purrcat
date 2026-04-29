BASH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Bash",
        "description": "在安全的沙盒环境 (Docker) 中执行 Shell 命令。你可以使用此工具进行环境配置、代码运行、文件操作等。注意：每次使用 cat >> 写入文件时，严禁超过 50 行代码，写完必须结束当前调用，在下一次回复中继续追加。",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 Shell 命令（支持连串命令和多行文本，请注意正确的引号转义）"
                },
                "timeout": {
                    "type": "integer",
                    "description": "命令执行的超时时间（秒），如果不确定请不要传，默认 300 秒"
                }
            },
            "required": ["command"]
        }
    }
}
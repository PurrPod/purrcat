CRON_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Cron",
        "description": "定时闹钟工具，支持添加、删除、修改和查询闹钟",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型：list（查询所有闹钟）、add（添加闹钟）、delete（删除闹钟）、update（修改闹钟）",
                    "enum": ["list", "add", "delete", "update"]
                },
                "name": {
                    "type": "string",
                    "description": "闹钟名称/标题（add 时为标题，delete/update 时为闹钟 ID）"
                },
                "trigger_time": {
                    "type": "string",
                    "description": "触发时间，HH:MM 格式（如 08:30），add 和 update 操作时使用"
                },
                "repeat_rule": {
                    "type": "string",
                    "description": "重复规则：none（不重复）、everyday（每天）、weekly_1~7（每周一到周日）",
                    "enum": ["none", "everyday", "weekly_1", "weekly_2", "weekly_3", 
                             "weekly_4", "weekly_5", "weekly_6", "weekly_7"],
                    "default": "none"
                },
                "active": {
                    "type": "boolean",
                    "description": "是否激活闹钟，update 操作时使用"
                }
            },
            "required": ["action"],
            "additionalProperties": False
        }
    }
}
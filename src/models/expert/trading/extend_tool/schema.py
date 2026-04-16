EXTEND_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_data",
            "description": "获取指定股票在特定日期的价格和技术指标数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "description": "股票代码或公司名称，如 AAPL"},
                    "trade_date": {"type": "string", "description": "交易日期，如 'Current' 或具体日期"}
                },
                "required": ["stock_code", "trade_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_on_social_media",
            "description": "在社交媒体上搜索关于特定资产的相关情绪和讨论",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "社交媒体平台，如 Twitter, Reddit"},
                    "query": {"type": "string", "description": "搜索的关键词，如股票名称或代码"}
                },
                "required": ["source", "query"]
            }
        }
    }
]
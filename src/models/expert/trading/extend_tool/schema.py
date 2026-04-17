EXTEND_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_data",
            "description": "获取 A 股特定股票的真实盘口行情、涨跌幅、换手率及市值数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {
                        "type": "string",
                        "description": "A股代码，可输入纯数字（如 000001, 600519）或带前缀（如 sz000001）"
                    },
                    "trade_date": {
                        "type": "string",
                        "description": "交易日期，通常填 'Current' 获取最新行情"
                    }
                },
                "required": ["stock_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_on_social_media",
            "description": "搜索特定个股、行业板块（如算力、半导体）的最新网络资讯、研报和市场情绪。",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "搜索信息源，如 'Web', 'News'"
                    },
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，例如 '中际旭创 CPO' 或 '诺安先锋半导体'"
                    }
                },
                "required": ["source", "query"]
            }
        }
    }
]
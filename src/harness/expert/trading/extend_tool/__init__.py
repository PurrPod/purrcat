"""
Trading Expert 扩展工具集

最小化原则：仅保留 2 个核心数据工具

工具清单:
  1. get_stock_data   — 统一数据查询 (行情+技术+基本面, mode参数控制)
  2. get_market_info  — 市场信息 (北向资金+热门排行+大盘指数)
"""
import json
from typing import Any

from .data_sources import get_stock_data as _get_stock_data
from .data_sources import get_market_info as _get_market_info

STOCK_DATA_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_stock_data",
        "description": "统一股票数据查询：实时行情 + 技术指标(MA/MACD/RSI/Bollinger/KDJ/ADX/ATR/OBV/WR) + 基本面(PE/市值)。支持A股(600519)和美股(AAPL)。mode参数控制返回范围。",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "股票代码 (A股纯数字如600519, 美股代码如AAPL)"},
                "mode": {
                    "type": "string",
                    "description": "数据模式: 'price'(仅行情) / 'tech'(行情+技术) / 'fundamental'(行情+基本面) / 'all'(全部)",
                    "enum": ["price", "tech", "fundamental", "all"]
                }
            },
            "required": ["code"]
        }
    }
}

MARKET_INFO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_market_info",
        "description": "获取市场整体信息：北向资金流向、百度热门股票排行、大盘指数行情。用于判断市场整体情绪和风向。",
        "parameters": {
            "type": "object",
            "properties": {
                "indicator": {
                    "type": "string",
                    "description": "信息类型: 'all'(全部) / 'sentiment'(北向资金) / 'hot'(热门排行) / 'index'(大盘指数)",
                    "enum": ["all", "sentiment", "hot", "index"]
                }
            },
            "required": ["indicator"]
        }
    }
}

EXTEND_TOOLS_SCHEMA = [STOCK_DATA_SCHEMA, MARKET_INFO_SCHEMA]

EXTEND_TOOL_FUNCTIONS = {
    "get_stock_data": lambda a, t=None: json.dumps({"type": "text", "content": _get_stock_data(a.get("code",""), a.get("mode","all"))}),
    "get_market_info": lambda a, t=None: json.dumps({"type": "text", "content": _get_market_info(a.get("indicator","all"))}),
}

def handle_extend_tool(tool_name: str, arguments: dict, task: Any) -> tuple[bool, str]:
    if tool_name in EXTEND_TOOL_FUNCTIONS:
        return True, EXTEND_TOOL_FUNCTIONS[tool_name](arguments, task)
    return False, ""

def get_extend_tools_schema() -> list[dict]:
    return EXTEND_TOOLS_SCHEMA

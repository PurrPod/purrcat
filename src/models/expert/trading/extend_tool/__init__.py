from .mock import get_stock_data, search_on_social_media
from .schema import EXTEND_TOOLS_SCHEMA

EXTEND_TOOL_FUNCTIONS = {
    "get_stock_data": get_stock_data,
    "search_on_social_media": search_on_social_media
}

__all__ = ["EXTEND_TOOL_FUNCTIONS", "EXTEND_TOOLS_SCHEMA"]
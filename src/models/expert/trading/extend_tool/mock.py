import requests
import re
import logging

logger = logging.getLogger(__name__)

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

def get_stock_data(stock_code: str, trade_date: str = "Current") -> str:
    """
    获取 A 股真实行情数据。
    使用腾讯财经轻量级 API，避免引入庞大的第三方数据包，极大降低环境依赖。
    """
    if stock_code.isdigit():
        prefix = 'sh' if stock_code.startswith('6') else 'sz'
        stock_code = prefix + stock_code
    url = f"http://qt.gtimg.cn/q={stock_code.lower()}"

    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200 and 'v_' in resp.text and len(resp.text) > 20:
            data_str = resp.text.split('=')[1].strip('";\n')
            fields = data_str.split('~')
            if len(fields) > 45:
                name = fields[1]  # 股票名称
                current_price = fields[3]  # 当前价格
                change_pct = fields[32]  # 涨跌幅 %
                turnover_rate = fields[38]  # 换手率 %
                market_cap = fields[45]  # 总市值 (亿)
                pe_ratio = fields[39]  # 市盈率 (TTM)
                return (
                    f"【{name} ({stock_code})】最新行情:\n"
                    f"- 现价: {current_price}元 (涨跌幅: {change_pct}%)\n"
                    f"- 换手率: {turnover_rate}%\n"
                    f"- 动态市盈率: {pe_ratio}\n"
                    f"- 总市值: {market_cap}亿元\n"
                    f"(注: 数据获取时间为 {trade_date})"
                )
        return f"未找到代码为 {stock_code} 的股票数据，请确保输入正确（如：600519 或 sh600519）。"
    except Exception as e:
        logger.error(f"行情接口请求失败: {e}")
        return f"Tool Execution Error: 网络请求失败 - {str(e)}"


def search_on_social_media(source: str, query: str) -> str:
    """
    抓取特定资产或板块（如“中际旭创 CPO”、“半导体 先锋”）的最新网络情绪和新闻。
    通过正则解析纯 HTML，实现零配置、免 Key 的搜索工具。
    """
    search_query = f"{query} 行情 OR 研报 OR 情绪"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    url = f"https://html.duckduckgo.com/html/?q={search_query}"
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        resp.raise_for_status()
        results = []
        snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', resp.text, re.IGNORECASE | re.DOTALL)
        titles = re.findall(r'<h2 class="result__title">.*?<a[^>]*>(.*?)</a>', resp.text, re.IGNORECASE | re.DOTALL)
        for t, s in zip(titles[:4], snippets[:4]):
            clean_title = re.sub(r'<[^>]+>', '', t).strip()
            clean_snippet = re.sub(r'<[^>]+>', '', s).strip()
            clean_snippet = clean_snippet.replace('<b>', '').replace('</b>', '').replace('&#x27;', "'")
            if clean_title and clean_snippet:
                results.append(f"▪ {clean_title}\n  摘要: {clean_snippet}")
        if not results:
            return f"暂无关于 '{query}' 在 {source} 的近期热点讨论。"
        return f"关于 '{query}' 的近期市场搜索结果：\n" + "\n".join(results)

    except Exception as e:
        logger.error(f"搜索接口请求失败: {e}")
        return f"Tool Execution Error: 搜索请求失败 - {str(e)}"
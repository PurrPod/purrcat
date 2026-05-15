"""Web 内容获取模块 - 仅负责获取指定 URL 网页内容并解析为高质量 Markdown"""

from typing import Dict, Optional, Tuple

from bs4 import BeautifulSoup
from curl_cffi import requests
from markdownify import markdownify as md
from readability import Document

from .exceptions import WebNetworkError

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}


def web_content_fetch(url: str) -> Tuple[Optional[Dict], Optional[str]]:
    """
    获取单页面 URL 内容并使用 Readability 提取纯净正文
    """
    try:
        response = requests.get(
            url, headers=DEFAULT_HEADERS, timeout=15, impersonate="chrome"
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()

        if "text/html" in content_type:
            html_content = response.text

            doc = Document(html_content)
            clean_html = doc.summary()
            title = doc.title() if doc.title() else url

            markdown_text = md(
                clean_html,
                heading_style="ATX",
                strip=["script", "style", "iframe", "nav", "footer"],
            )
            markdown_text = "\n".join(
                [line for line in markdown_text.splitlines() if line.strip() != ""]
            )

            if len(markdown_text) < 50:
                soup = BeautifulSoup(html_content, "html.parser")
                title = soup.title.string if soup.title else url
                paragraphs = soup.find_all(["article", "main", "div.content", "p"])
                markdown_text = "\n".join([p.get_text(strip=True) for p in paragraphs])

            final_content = (
                markdown_text[:10000] if len(markdown_text) > 10000 else markdown_text
            )

            return {
                "url": url,
                "title": title,
                "content": f"# {title}\n\n{final_content}",
                "content_type": "html",
            }, None

        elif "application/json" in content_type:
            return {
                "url": url,
                "title": "JSON Data",
                "content": response.json(),
                "content_type": "json",
            }, None

        else:
            raw_text = (
                response.text
                if isinstance(response.text, str)
                else str(response.content)
            )
            return {
                "url": url,
                "title": "Raw Data",
                "content": raw_text[:5000],
                "content_type": content_type,
            }, None

    except requests.exceptions.RequestException:
        raise WebNetworkError()
    except WebNetworkError:
        raise
    except Exception as e:
        return None, f"解析失败: {str(e)}"

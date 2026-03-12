import json
import os
import uuid
from typing import Any

import requests
import warnings
import datetime

with warnings.catch_warnings():
    warnings.simplefilter("ignore", RuntimeWarning)
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            DDGS = None

with open("data\config\web_config.json","r") as f:
    config = json.load(f)
os.environ["TAVILY_API_KEY"] = config["TAVILY_API_KEY"]
_tool_instance = None
def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)
def get_tool():
    global _tool_instance
    if _tool_instance is None:
        # 默认 buffer 路径在当前文件所在目录下的 buffer 文件夹
        _tool_instance = WebTools(buffer_path=os.path.join(os.path.dirname(__file__), "buffer"))
    return _tool_instance

class WebTools:
    def __init__(self, buffer_path: str = "data\\buffer"):
        self.buffer_path = os.path.abspath(buffer_path)
        if not os.path.exists(self.buffer_path):
            os.makedirs(self.buffer_path)


    def _save_to_buffer(self, content: str, prefix: str = "fetch") -> str:
        marker_id = uuid.uuid4().hex[:10]
        timestamp = datetime.datetime.now().strftime("%Y%m%d")
        filename = f"{prefix}_{timestamp}{marker_id}.md"
        file_path = os.path.join(self.buffer_path, filename)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        return file_path

    def web_search(self, query: str, max_results: int = 5) -> str:
        """
        高可用网页搜索：优先 Tavily API -> 降级 Google API -> 降级 DDGS
        请在环境变量中设置 TAVILY_API_KEY, GOOGLE_API_KEY, GOOGLE_CX
        """
        results = []
        error_logs = []

        # 优先级 1: Tavily API
        tavily_key = os.environ.get("TAVILY_API_KEY")
        if tavily_key:
            try:
                headers = {"Content-Type": "application/json"}
                data = {"api_key": tavily_key, "query": query, "search_depth": "basic", "max_results": max_results}
                resp = requests.post("https://api.tavily.com/search", json=data, timeout=10)

                if resp.status_code == 200:
                    tavily_data = resp.json()
                    for res in tavily_data.get("results", []):
                        results.append({"title": res["title"], "url": res["url"], "snippet": res["content"]})
                    
                    md_content = f"# Search Results for: {query}\n\n"
                    for res in results:
                        md_content += f"## {res['title']}\n- URL: {res['url']}\n- Snippet: {res['snippet']}\n\n"
                    file_path = self._save_to_buffer(md_content, prefix="search")
                    return f"已将结果存放至文件{file_path}"
                else:
                    error_logs.append(f"Tavily API Error: {resp.status_code} - {resp.text}")
            except Exception as e:
                error_logs.append(f"Tavily API Exception: {str(e)}")

        # 优先级 2: Google Custom Search API
        google_key = os.environ.get("GOOGLE_API_KEY")
        google_cx = os.environ.get("GOOGLE_CX")
        if google_key and google_cx:
            try:
                url = f"https://www.googleapis.com/customsearch/v1?key={google_key}&cx={google_cx}&q={requests.utils.quote(query)}&num={max_results}"
                resp = requests.get(url, timeout=10)

                if resp.status_code == 200:
                    google_data = resp.json()
                    for item in google_data.get("items", []):
                        results.append(
                            {"title": item.get("title"), "url": item.get("link"), "snippet": item.get("snippet")})
                    
                    md_content = f"# Search Results for: {query}\n\n"
                    for res in results:
                        md_content += f"## {res['title']}\n- URL: {res['url']}\n- Snippet: {res['snippet']}\n\n"
                    file_path = self._save_to_buffer(md_content, prefix="search")
                    return f"已将结果存放至文件{file_path}"
                else:
                    error_logs.append(f"Google API Error: {resp.status_code} - {resp.text}")
            except Exception as e:
                error_logs.append(f"Google API Exception: {str(e)}")

        # 优先级 3: DDGS 无需验证的白嫖方案
        try:
            if DDGS:
                with DDGS() as ddgs:
                    ddg_results = list(ddgs.text(query, max_results=max_results))
                    if ddg_results:
                        for r in ddg_results:
                            results.append(
                                {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")})
                        
                        md_content = f"# Search Results for: {query}\n\n"
                        for res in results:
                            md_content += f"## {res['title']}\n- URL: {res['url']}\n- Snippet: {res['snippet']}\n\n"
                        file_path = self._save_to_buffer(md_content, prefix="search")
                        return f"已将结果存放至文件{file_path}"
        except Exception as e:
            error_logs.append(f"DDGS Fallback Exception: {str(e)}")

        # 如果全军覆没，返回所有错误日志，方便你排查是不是 Key 没配对或者网络断了
        return json.dumps({
            "type": "error",
            "content": f"All web APIs failed. Please check your network or API Keys. Logs: {' | '.join(error_logs)}"
        }, ensure_ascii=False)

    def fetch_web_content(self, url: str) -> str:
        """
        高纯度网页内容提取：优先 Jina Reader API (完美 Markdown) -> 降级本地 BeautifulSoup
        """
        # 优先级 1: Jina Reader API
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            jina_url = f"https://r.jina.ai/{url}"
            resp = requests.get(jina_url, headers=headers, timeout=15)

            if resp.status_code == 200:
                content = resp.text
                file_path = self._save_to_buffer(content, prefix="fetch")
                return _format_response("text", "已将结果存放至文件{file_path}")
        except Exception as e:
            print(f"⚠️ Jina API failed: {e}. Falling back to local scraper...")

        # 优先级 2: 本地 BeautifulSoup 暴力清洗
        try:
            from bs4 import BeautifulSoup
            import html2text

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0"}
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding

            soup = BeautifulSoup(resp.text, 'html.parser')
            tags_to_remove = ["script", "style", "noscript", "nav", "footer", "header", "aside", "iframe"]
            for tag in soup(tags_to_remove):
                tag.decompose()

            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.body_width = 0

            clean_text = h.handle(str(soup))
            lines = [line.strip() for line in clean_text.splitlines()]
            final_text = "\n".join(line for line in lines if line)


            file_path = self._save_to_buffer(final_text, prefix="fetch")
            return _format_response("text",f"已将结果存放至文件{file_path}")

        except Exception as e:
            return json.dumps({"type": "error", "content": f"Failed to fetch content from {url}: {str(e)}"},
                              ensure_ascii=False)

# Top-level wrappers
def web_search(query: str, max_results: int = 5) -> str:
    return get_tool().web_search(query, max_results)

def fetch_web_content(url: str) -> str:
    return get_tool().fetch_web_content(url)


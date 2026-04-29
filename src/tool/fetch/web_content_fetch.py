"""Web 内容获取模块 - 获取网页内容并解析为文本"""

import requests
from typing import Dict


def web_content_fetch(url: str) -> tuple:
    """
    获取网页内容并解析
    
    Args:
        url: 网页 URL
    
    Returns:
        (content_dict, error_message) - content_dict 包含标题、正文等信息
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        content_type = response.headers.get('Content-Type', '')
        
        # 尝试解析 HTML
        if 'text/html' in content_type:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # 获取标题
                title = soup.title.string if soup.title else url
                
                # 获取正文（优先选择常见的内容标签）
                content_tags = soup.find_all(['article', 'main', 'div.content', 'div.main', 'div.post-content'])
                
                if content_tags:
                    text_content = '\n'.join([tag.get_text(strip=True) for tag in content_tags])
                else:
                    # 如果找不到特定标签，提取所有段落
                    paragraphs = soup.find_all('p')
                    text_content = '\n'.join([p.get_text(strip=True) for p in paragraphs])
                
                # 清理文本
                text_content = '\n'.join([line.strip() for line in text_content.split('\n') if line.strip()])
                
                return {
                    "url": url,
                    "title": title,
                    "content": text_content[:5000] if len(text_content) > 5000 else text_content,
                    "content_type": "html"
                }, None
                
            except ImportError:
                # 如果没有 BeautifulSoup，直接返回文本内容
                return {
                    "url": url,
                    "title": url,
                    "content": response.text[:5000],
                    "content_type": "text"
                }, None
        
        elif 'application/json' in content_type:
            return {
                "url": url,
                "title": url,
                "content": response.json(),
                "content_type": "json"
            }, None
        
        else:
            # 其他类型，返回原始内容的前 5000 字符
            return {
                "url": url,
                "title": url,
                "content": response.text[:5000] if isinstance(response.text, str) else str(response.content[:5000]),
                "content_type": content_type
            }, None
            
    except requests.exceptions.RequestException as e:
        return None, f"请求失败: {str(e)}"
    except Exception as e:
        return None, f"解析失败: {str(e)}"
import asyncio
from typing import Dict, Tuple, Optional
from bs4 import BeautifulSoup
from readability import Document
from markdownify import markdownify as md
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

async def web_content_fetch_playwright(url: str, timeout_ms: int = 30000) -> Tuple[Optional[Dict], Optional[str]]:
    """
    使用 Playwright 抓取动态渲染网页，支持 SPA 渲染、自动滚动和反爬墙识别。
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # 使用 networkidle 确保 SPA 网站的动态请求加载完毕
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            # 超时后不抛出异常，继续处理已经加载出来的页面
            pass

        # ----------------------------------------------------------------
        # 反爬墙/验证码识别 (Cloudflare, reCAPTCHA, hCaptcha 等)
        # ----------------------------------------------------------------
        is_blocked = await page.evaluate('''() => {
            const selectors = [
                '.cf-turnstile', '[name="cf-turnstile-response"]', 'iframe[src*="challenges.cloudflare.com"]',
                '#challenge-running', '#cf-challenge-running',
                '.g-recaptcha', 'textarea[name="g-recaptcha-response"]', 'iframe[src*="google.com/recaptcha"]',
                '.h-captcha', 'textarea[name="h-captcha-response"]', 'iframe[src*="hcaptcha.com"]'
            ];
            const text = document.body ? document.body.innerText.toLowerCase() : "";
            const title = document.title.toLowerCase();
            
            return selectors.some(selector => document.querySelector(selector) !== null) || 
                   title.includes("just a moment") || 
                   text.includes("verify you are human") ||
                   text.includes("checking your browser before accessing");
        }''')

        if is_blocked:
            await browser.close()
            # 直接返回给 Agent，明确告知被反爬拦截，建议换工具
            return {
                "url": url,
                "title": "Blocked by Anti-bot",
                "content": f"# 访问受限\n\n**URL:** {url}\n\n---\n\n⚠️ 网页被 Cloudflare、reCAPTCHA 或其他反爬机制拦截，无法自动获取内容。请尝试使用其他工具（如 Google 搜索或专用 API）获取相关信息。",
                "content_type": "error"
            }, None

        # ----------------------------------------------------------------
        # 模拟滚动，触发图片懒加载和到底部的动态请求
        # ----------------------------------------------------------------
        await page.evaluate('''
            async () => {
                await new Promise((resolve) => {
                    let totalHeight = 0;
                    let distance = 800;
                    let timer = setInterval(() => {
                        let scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        if(totalHeight >= scrollHeight - window.innerHeight){
                            clearInterval(timer);
                            resolve();
                        }
                    }, 200);
                });
            }
        ''')
        await page.wait_for_timeout(1000)

        html_content = await page.content()
        title = await page.title()
        await browser.close()

    # ----------------------------------------------------------------
    # Readability 提取正文并转 Markdown（取消任何字符数截断）
    # ----------------------------------------------------------------
    doc = Document(html_content)
    clean_html = doc.summary()
    doc_title = doc.title() if doc.title() else title

    markdown_text = md(
        clean_html,
        heading_style="ATX",
        strip=["script", "style", "iframe", "nav", "footer", "noscript"]
    )
    
    # 清理多余空行
    markdown_text = "\n".join([line for line in markdown_text.splitlines() if line.strip() != ""])

    # 降级处理：如果 Readability 提取失败（例如正文极短），则尝试提取所有文本
    if len(markdown_text) < 50:
        soup = BeautifulSoup(html_content, "html.parser")
        doc_title = soup.title.string if soup.title else url
        paragraphs = soup.find_all(["article", "main", "div.content", "p", "div"])
        markdown_text = "\n\n".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])

    # 完全移除切片限制 [:2000] 或 [:10000]，保留全量 Markdown
    final_content = markdown_text

    return {
        "url": url,
        "title": doc_title,
        "content": f"# {doc_title}\n\n**URL:** {url}\n**类型:** html\n---\n\n{final_content}",
        "content_type": "html"
    }, None

# 如果你在同步函数中调用，可以使用一个包装器：
def web_content_fetch(url: str) -> Tuple[Optional[Dict], Optional[str]]:
    """
    提供给原系统的同步接口入口
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    try:
        result, error = loop.run_until_complete(web_content_fetch_playwright(url))
        return result, error
    except Exception as e:
        return None, f"Playwright 抓取失败: {str(e)}"
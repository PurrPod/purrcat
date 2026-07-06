import asyncio
import re
from typing import Dict, Tuple, Optional
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

async def web_content_fetch_playwright(url: str, timeout_ms: int = 30000) -> Tuple[Optional[Dict], Optional[str]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            pass

        # ----------------------------------------------------------------
        # 1. 拦截识别（加上了 r，防止转义）
        # ----------------------------------------------------------------
        is_blocked = await page.evaluate(r'''() => {
            const selectors = ['.cf-turnstile', '[name="cf-turnstile-response"]', 'iframe[src*="challenges.cloudflare.com"]', '#challenge-running', '#cf-challenge-running'];
            const text = document.body ? document.body.innerText.toLowerCase() : "";
            return selectors.some(s => document.querySelector(s) !== null) || text.includes("verify you are human");
        }''')

        if is_blocked:
            await browser.close()
            return {
                "url": url,
                "title": "Blocked by Anti-bot",
                "content": f"# 访问受限\n\n**URL:** {url}\n\n⚠️ 网页被反爬机制拦截，无法自动获取。请尝试其他工具。",
                "content_type": "error"
            }, None

        # ----------------------------------------------------------------
        # 2. 模拟向下平滑滚动（加上了 r，防止转义）
        # ----------------------------------------------------------------
        await page.evaluate(r'''
            async () => {
                await new Promise((resolve) => {
                    let totalHeight = 0;
                    let distance = 1000;
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

        # ----------------------------------------------------------------
        # 3. 核心大招：拍平 Shadow DOM（加上了 r，解决 SyntaxError）[cite: 1]
        # ----------------------------------------------------------------
        snapshot_data = await page.evaluate(r'''() => {
            const baseUrl = document.baseURI || location.href;
            const htmlClone = document.documentElement.cloneNode(true);
            
            function materializeShadowDom(sourceRoot, cloneRoot) {
                const sourceElements = Array.from(sourceRoot.querySelectorAll("*"));
                const cloneElements = Array.from(cloneRoot.querySelectorAll("*"));
                for (let index = sourceElements.length - 1; index >= 0; index -= 1) {
                    const sourceElement = sourceElements[index];
                    const cloneElement = cloneElements[index];
                    const shadowRoot = sourceElement && sourceElement.shadowRoot;
                    if (!shadowRoot || !cloneElement || !shadowRoot.innerHTML) {
                        continue;
                    }
                    if (cloneElement.tagName && cloneElement.tagName.includes("-")) {
                        const wrapper = document.createElement("div");
                        wrapper.setAttribute("data-shadow-host", cloneElement.tagName.toLowerCase());
                        wrapper.innerHTML = shadowRoot.innerHTML;
                        cloneElement.replaceWith(wrapper);
                    } else {
                        cloneElement.innerHTML = shadowRoot.innerHTML;
                    }
                }
            }
            
            function toAbsolute(url) {
                if (!url) return url;
                try { return new URL(url, baseUrl).href; } catch { return url; }
            }
            
            function absolutizeAttribute(root, selector, attribute) {
                root.querySelectorAll(selector).forEach((element) => {
                    const value = element.getAttribute(attribute);
                    if (!value) return;
                    const absolute = toAbsolute(value);
                    if (absolute) element.setAttribute(attribute, absolute);
                });
            }

            materializeShadowDom(document.documentElement, htmlClone);
            
            htmlClone.querySelectorAll("img[data-src], video[data-src], source[data-src]")
                .forEach((element) => {
                    const dataSource = element.getAttribute("data-src");
                    const current = element.getAttribute("src");
                    if (dataSource && (!current || current === "" || current.startsWith("data:"))) {
                        element.setAttribute("src", dataSource);
                    }
                });
                
            absolutizeAttribute(htmlClone, "a[href]", "href");
            absolutizeAttribute(htmlClone, "img[src], video[src], source[src]", "src");
            
            return {
                html: "<!doctype html>\\n" + htmlClone.outerHTML,
                finalUrl: location.href
            };
        }''')

        html_content = snapshot_data["html"]
        final_url = snapshot_data["finalUrl"]
        await browser.close()

    # ----------------------------------------------------------------
    # 4. 智能解析与清洗（抛弃易误杀的 Readability，采用精准剪裁策略）
    # ----------------------------------------------------------------
    soup = BeautifulSoup(html_content, "html.parser")
    doc_title = soup.title.string if soup.title else final_url
    
    # 第一步：强力清洗非正文噪音标签
    # 移除脚本、样式、导航、页脚、侧边栏、弹窗、SVG 图标等
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "nav", "footer", "header", "aside"]):
        tag.decompose()
        
    # 第二步：定位核心内容区
    # 现代网站通常会将正文包裹在 main、article 或 id/class 包含 content 的 div 中
    main_content = soup.find("main") or soup.find("article")
    if not main_content:
        # 如果找不到标准语义标签，退而求其次用 body，前面的清洗已经去掉了大部分干扰
        main_content = soup.find("body") or soup

    # 第三步：直接将清洗后的 HTML 对象交给 markdownify 转换
    # 这样能完美保留 #标题、- 列表、```代码块 等原汁原味的 Markdown 排版
    markdown_text = md(str(main_content), heading_style="ATX")
    
    # 第四步：格式优化，清理连续的多余空行
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text).strip()

    # 兜底策略：如果提取结果过短，使用简化版逐段提取
    if len(markdown_text) < 150:
        paragraphs = soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "code", "div"])
        text_lines = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text and text not in text_lines:
                text_lines.append(text)
        markdown_text = "\n\n".join(text_lines)

    return {
        "url": url,
        "title": doc_title,
        "content": markdown_text,
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
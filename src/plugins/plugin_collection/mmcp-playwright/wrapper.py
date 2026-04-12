import os
import json
import asyncio
import base64
import html2text
from collections import deque
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Playwright, Response, expect

# === 配置 ===
# 文件保存根目录
BASE_PATH = os.path.abspath(os.path.join(os.getcwd(), "downloads"))
if not os.path.exists(BASE_PATH):
    os.makedirs(BASE_PATH)

# === 全局状态 ===
_playwright: Playwright = None
_browser: Browser = None
_context: BrowserContext = None
_page: Page = None  # 当前激活的页面

_h2t = html2text.HTML2Text()
_h2t.ignore_links = False
_h2t.body_width = 0

# 网络日志缓冲区
_network_logs = deque(maxlen=200)
# 控制台日志缓冲区
_console_logs = deque(maxlen=200)


# === 内部辅助函数 ===

def _resolve_path(user_file_path: str):
    """相对路径转绝对路径，确保安全"""
    clean_path = user_file_path.lstrip("/\\")
    full_path = os.path.join(BASE_PATH, clean_path)
    parent_dir = os.path.dirname(full_path)
    if not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)
    return full_path


async def _on_response(response: Response):
    """网络监听回调"""
    if response.request.resource_type in ["xhr", "fetch", "document"]:
        try:
            # 尝试获取文本或JSON
            text = await response.text()
            # ✅ 删除预览截断，保存完整内容
            preview = text
        except:
            preview = "[Binary Data]"

        _network_logs.append({
            "url": response.url,
            "method": response.request.method,
            "status": response.status,
            "type": response.request.resource_type,
            "preview": preview
        })


def _on_console(msg):
    """控制台监听回调"""
    _console_logs.append(f"[{msg.type}] {msg.text}")


async def _ensure_page():
    global _playwright, _browser, _context, _page
    if _playwright is None:
        _playwright = await async_playwright().start()

    if _browser is None:
        # 默认无头模式，如需观察改为 headless=False
        _browser = await _playwright.chromium.launch(headless=True, downloads_path=BASE_PATH)

    if _context is None:
        _context = await _browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        # 开启 Tracing 预备
        await _context.tracing.start(screenshots=True, snapshots=True)

    if _page is None:
        if len(_context.pages) > 0:
            _page = _context.pages[0]
        else:
            _page = await _context.new_page()

        # 挂载监听器
        _page.on("response", _on_response)
        _page.on("console", _on_console)

    return _page


def _success(data=None, msg="success"):
    return json.dumps({"status": "success", "message": msg, "data": data}, ensure_ascii=False)


def _error(msg):
    return json.dumps({"status": "error", "message": str(msg)}, ensure_ascii=False)


# === 1. 核心自动化 (Core Automation) ===

async def browser_navigate(url: str):
    try:
        global _network_logs, _console_logs
        _network_logs.clear()
        _console_logs.clear()
        page = await _ensure_page()
        await page.goto(url, timeout=100000, wait_until="domcontentloaded")
        return _success({"title": await page.title(), "url": page.url}, "Navigated")
    except Exception as e:
        return _error(e)


async def browser_navigate_back():
    try:
        page = await _ensure_page()
        await page.go_back()
        return _success(msg="Navigated back")
    except Exception as e:
        return _error(e)


async def browser_snapshot():
    """获取页面快照（核心：Markdown预览）"""
    try:
        page = await _ensure_page()
        html = await page.content()
        markdown = _h2t.handle(html)[:10000]  # 限制长度
        return _success({"snapshot": markdown}, "Snapshot taken")
    except Exception as e:
        return _error(e)


async def browser_take_screenshot(file_path: str, full_page: bool = False):
    try:
        page = await _ensure_page()
        bytes_data = await page.screenshot(full_page=full_page)
        b64_str = base64.b64encode(bytes_data).decode('utf-8')
        return _success({"type": "image", "ext": ".png", "data": b64_str}, "Screenshot taken")
    except Exception as e:
        return _error(e)


async def browser_click(selector: str):
    try:
        page = await _ensure_page()
        # 官方 ref 参数这里简化为 selector，LLM 传选择器即可
        await page.click(selector, timeout=5000)
        return _success(msg=f"Clicked {selector}")
    except Exception as e:
        return _error(e)


async def browser_type(selector: str, text: str, submit: bool = False):
    try:
        page = await _ensure_page()
        await page.fill(selector, text, timeout=5000)
        if submit:
            await page.press(selector, "Enter")
        return _success(msg=f"Typed into {selector}")
    except Exception as e:
        return _error(e)


async def browser_fill_form(fields: list):
    """自动填表: fields=[{'selector': '#id', 'value': 'val'}, ...]"""
    try:
        page = await _ensure_page()
        for field in fields:
            await page.fill(field['selector'], field['value'])
        return _success(msg="Form filled")
    except Exception as e:
        return _error(e)


async def browser_select_option(selector: str, value: str):
    try:
        page = await _ensure_page()
        await page.select_option(selector, value)
        return _success(msg=f"Selected {value}")
    except Exception as e:
        return _error(e)


async def browser_hover(selector: str):
    try:
        page = await _ensure_page()
        await page.hover(selector)
        return _success(msg=f"Hovered {selector}")
    except Exception as e:
        return _error(e)


async def browser_drag(start_selector: str, end_selector: str):
    try:
        page = await _ensure_page()
        await page.drag_and_drop(start_selector, end_selector)
        return _success(msg="Drag and drop completed")
    except Exception as e:
        return _error(e)


async def browser_press_key(key: str):
    try:
        page = await _ensure_page()
        await page.keyboard.press(key)
        return _success(msg=f"Pressed {key}")
    except Exception as e:
        return _error(e)


async def browser_evaluate(script: str):
    try:
        page = await _ensure_page()
        res = await page.evaluate(script)
        return _success(res, "JS executed")
    except Exception as e:
        return _error(e)


async def browser_run_code(code: str):
    """危险：直接运行 Playwright Python 代码"""
    try:
        page = await _ensure_page()
        # 定义安全的局部变量
        local_scope = {'page': page, 'playwright': _playwright}
        exec(code, {}, local_scope)
        return _success(msg="Code executed successfully")
    except Exception as e:
        return _error(e)


async def browser_console_messages(level: str = None):
    return _success(list(_console_logs), "Console logs")


async def browser_network_requests(include_static: bool = False):
    return _success(list(_network_logs), "Network logs")


async def browser_wait_for(selector: str, timeout: int = 5000):
    try:
        page = await _ensure_page()
        await page.wait_for_selector(selector, timeout=timeout)
        return _success(msg=f"Element {selector} appeared")
    except Exception as e:
        return _error(e)


async def browser_handle_dialog(accept: bool = True, prompt_text: str = None):
    try:
        page = await _ensure_page()

        def handle(dialog):
            if accept:
                asyncio.create_task(dialog.accept(prompt_text))
            else:
                asyncio.create_task(dialog.dismiss())

        page.once("dialog", handle)
        return _success(msg="Dialog handler registered (will apply to next dialog)")
    except Exception as e:
        return _error(e)


async def browser_file_upload(selector: str, file_path: str):
    try:
        page = await _ensure_page()
        path = _resolve_path(file_path)
        await page.set_input_files(selector, path)
        return _success(msg=f"Uploaded {path}")
    except Exception as e:
        return _error(e)


async def browser_resize(width: int, height: int):
    try:
        page = await _ensure_page()
        await page.set_viewport_size({"width": width, "height": height})
        return _success(msg="Resized")
    except Exception as e:
        return _error(e)


async def browser_close():
    try:
        global _page
        if _page:
            await _page.close()
            _page = None
        return _success(msg="Page closed")
    except Exception as e:
        return _error(e)


# === 2. 标签页管理 (Tab Management) ===

async def browser_tabs(action: str, index: int = None):
    """
    action: 'list', 'create', 'switch', 'close'
    """
    global _page, _context
    try:
        await _ensure_page()
        pages = _context.pages

        if action == 'list':
            info = [{"index": i, "title": await p.title(), "url": p.url} for i, p in enumerate(pages)]
            return _success(info, "Tab list")

        elif action == 'create':
            _page = await _context.new_page()
            # 重新挂载监听
            _page.on("response", _on_response)
            _page.on("console", _on_console)
            return _success({"index": len(pages)}, "Tab created")

        elif action == 'switch':
            if index is not None and 0 <= index < len(pages):
                _page = pages[index]
                await _page.bring_to_front()
                return _success(msg=f"Switched to tab {index}")
            return _error("Invalid index")

        elif action == 'close':
            if index is not None and 0 <= index < len(pages):
                await pages[index].close()
                if pages[index] == _page:
                    _page = _context.pages[-1] if _context.pages else None
                return _success(msg=f"Closed tab {index}")
            return _error("Invalid index")

    except Exception as e:
        return _error(e)


# === 3. 浏览器安装 (Install) ===

async def browser_install():
    try:
        proc = await asyncio.create_subprocess_shell(
            "playwright install chromium",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return _success(msg="Browser installed")
    except Exception as e:
        return _error(e)


# === 4. 视觉坐标操作 (Coordinate-based) ===

async def browser_mouse_click_xy(x: float, y: float):
    try:
        page = await _ensure_page()
        await page.mouse.click(x, y)
        return _success(msg=f"Clicked at {x},{y}")
    except Exception as e:
        return _error(e)


async def browser_mouse_move_xy(x: float, y: float):
    try:
        page = await _ensure_page()
        await page.mouse.move(x, y)
        return _success(msg=f"Moved to {x},{y}")
    except Exception as e:
        return _error(e)


async def browser_mouse_drag_xy(start_x: float, start_y: float, end_x: float, end_y: float):
    try:
        page = await _ensure_page()
        await page.mouse.move(start_x, start_y)
        await page.mouse.down()
        await page.mouse.move(end_x, end_y)
        await page.mouse.up()
        return _success(msg="Dragged coordinates")
    except Exception as e:
        return _error(e)


# === 5. PDF 生成 ===

async def browser_pdf_save(file_path: str):
    try:
        page = await _ensure_page()
        pdf_bytes = await page.pdf()
        b64_str = base64.b64encode(pdf_bytes).decode('utf-8')
        return _success({"type": "pdf", "ext": ".pdf", "data": b64_str}, "PDF generated")
    except Exception as e:
        return _error(e)


# === 6. 测试断言 (Assertions) ===

async def browser_verify_element_visible(selector: str):
    try:
        page = await _ensure_page()
        is_visible = await page.is_visible(selector)
        return _success({"visible": is_visible})
    except Exception as e:
        return _error(e)


async def browser_verify_text_visible(text: str):
    try:
        page = await _ensure_page()
        # 简单的文本查找
        found = await page.get_by_text(text).count() > 0
        return _success({"visible": found})
    except Exception as e:
        return _error(e)


async def browser_generate_locator(selector: str):
    # 简单返回 selector，因为 Playwright Python 没有内置生成器 API 暴露给普通用户
    return _success({"locator": selector})


# === 7. 追踪记录 (Tracing) ===

async def browser_start_tracing():
    try:
        global _context
        if _context:
            await _context.tracing.start(screenshots=True, snapshots=True)
        return _success(msg="Tracing started")
    except Exception as e:
        return _error(e)


async def browser_stop_tracing(file_path: str):
    try:
        global _context
        path = _resolve_path(file_path)
        if _context:
            await _context.tracing.stop(path=path)
        return _success({"saved_path": path}, "Tracing stopped and saved")
    except Exception as e:
        return _error(e)
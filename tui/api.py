# tui/api.py
import json
import os
import urllib.request
import asyncio
from urllib.error import URLError


def get_api_base() -> str:
    """完全对齐 WebUI store.ts: 从 backend_port.json 读取真实端口"""
    port = 8001
    port_file = os.path.join(os.getcwd(), "data", "backend_port.json")
    if os.path.exists(port_file):
        try:
            with open(port_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                port = data.get("port", port)
        except Exception:
            pass
    return f"http://127.0.0.1:{port}/api"


async def fetch_api(path: str, method: str = "GET", data: dict = None) -> dict | list:
    """标准库异步 HTTP 请求，对接 backend.py 路由"""
    url = get_api_base() + path
    req = urllib.request.Request(url, method=method)
    if data is not None:
        req.add_header('Content-Type', 'application/json')
        req.data = json.dumps(data).encode('utf-8')

    def _do_req():
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except URLError as e:
            return {"error": f"Backend unreachable: {e.reason}"}
        except Exception as e:
            return {"error": str(e)}

    return await asyncio.to_thread(_do_req)
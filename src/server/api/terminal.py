"""终端 WebSocket 桥接接口。

将 WebSocket 连接挂载到本地系统的 shell 或特定命令上，
配合前端 xterm.js 实现"网页内交互式终端"。
"""

import sys
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/terminal", tags=["Terminal WebSocket Bridge"])


def _default_shell() -> str:
    """根据平台返回默认的交互式 shell。"""
    if sys.platform.startswith("win"):
        return "powershell.exe -NoLogo"
    return "bash"


@router.websocket("/ws")
async def terminal_websocket(websocket: WebSocket, cmd: str | None = None):
    """
    将 WebSocket 连接挂载到本地系统的 shell 或特定命令上。

    query 参数:
        cmd: 可选，要启动的 shell/命令。不传则使用平台默认 (Windows: powershell, *nix: bash)。
    """
    await websocket.accept()

    shell_cmd = cmd if cmd else _default_shell()

    try:
        process = await asyncio.create_subprocess_shell(
            shell_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except Exception as e:
        await websocket.send_text(f"[Failed to start process] {e}\r\n")
        await websocket.close()
        return

    async def read_output():
        try:
            while True:
                data = await process.stdout.read(1024)
                if not data:
                    break
                await websocket.send_text(data.decode("utf-8", errors="replace"))
        except Exception:
            pass

    async def write_input():
        try:
            while True:
                data = await websocket.receive_text()
                if process.stdin is None:
                    continue
                process.stdin.write(data.encode("utf-8"))
                await process.stdin.drain()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    try:
        await asyncio.gather(read_output(), write_input())
    finally:
        if process.returncode is None:
            try:
                process.terminate()
            except Exception:
                pass

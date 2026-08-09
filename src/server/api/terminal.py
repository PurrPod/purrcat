"""终端 WebSocket 桥接接口 — 使用 PTY (伪终端)。

PTY 让 PowerShell/bash 认为自己在跟真终端对话，
从而启用 readline、backspace、tab 补全、颜色、提示符等所有交互特性。

- Windows: 使用 pywinpty (Microsoft 出品，VS Code/Jupyter 同款)
- *nix: 使用 pty 模块 (标准库)

控制消息协议：
  前端发来的消息以 \x00 (NULL) 开头的是控制消息 (JSON)，否则是 stdin 输入。
  例如: "\x00{"type":"resize","cols":120,"rows":30}"
"""

import sys
import os
import atexit
import signal
import asyncio
import json
import subprocess

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/terminal", tags=["Terminal WebSocket Bridge"])

# 全局跟踪所有活跃的 PTY 子进程 PID，用于主程序退出时统一清理
_active_pids: set[int] = set()


def _kill_pid_tree(pid: int):
    """杀掉指定 PID 及其所有子进程（Windows 用 taskkill /T）。"""
    try:
        if sys.platform.startswith("win"):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5,
            )
        else:
            os.kill(pid, signal.SIGKILL)
    except Exception:
        pass


def _cleanup_all_pty():
    """主程序退出时杀掉所有残留的终端子进程。"""
    for pid in list(_active_pids):
        _kill_pid_tree(pid)
    _active_pids.clear()


# 注册退出清理钩子 — Ctrl+C / 正常退出 / uvicorn shutdown 都会触发
atexit.register(_cleanup_all_pty)


# 平台相关的 PTY 导入
if sys.platform.startswith("win"):
    import winpty  # type: ignore
else:
    import pty as _pty_module  # type: ignore
    import select
    import termios
    import struct
    import fcntl


# Windows PowerShell 路径
_PS_PATH = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def _build_spawn_win(cmd: str | None) -> tuple[str, str]:
    """Windows: 返回 (appname, cmdline_string)。

    pywinpty 的 spawn(appname, cmdline=...) 要求 cmdline 是完整命令行字符串。
    """
    prog = _PS_PATH
    if cmd:
        escaped_cmd = cmd.replace('"', '`"')
        cmdline = f'"{prog}" -NoLogo -NoExit -Command "{escaped_cmd}"'
    else:
        cmdline = f'"{prog}" -NoLogo'
    return (prog, cmdline)


def _build_spawn_unix(cmd: str | None) -> tuple[str, list[str]]:
    """*nix: 返回 (program, argv_list)。

    默认用 $SHELL 环境变量（macOS Catalina+ 是 zsh，Linux 通常 bash）。
    """
    shell = os.environ.get("SHELL", "/bin/bash")
    if cmd:
        return (shell, [shell, "-c", cmd])
    return (shell, [shell])


# ─────────────────────────────────────────────
# Windows: pywinpty 实现
# ─────────────────────────────────────────────
async def _serve_winpty(websocket: WebSocket, cmd: str | None):
    cols, rows = 80, 24
    pty = winpty.PTY(cols=cols, rows=rows)

    appname, cmdline = _build_spawn_win(cmd)
    try:
        pty.spawn(appname, cmdline=cmdline, cwd=os.getcwd())
    except Exception as e:
        await websocket.send_text(f"\r\n\x1b[31m[Failed to spawn] {e}\x1b[0m\r\n")
        await websocket.close()
        return

    # 记录 PID 用于退出清理
    try:
        child_pid = pty.pid
        if child_pid:
            _active_pids.add(child_pid)
    except Exception:
        child_pid = None

    loop = asyncio.get_event_loop()
    # WebSocket 断开标志 — write_input 退出时设置，read_output 检测后退出
    disconnected = asyncio.Event()

    async def read_output():
        """从 PTY 读输出 → 发给前端。"""
        while True:
            if disconnected.is_set():
                break
            try:
                data = await loop.run_in_executor(None, pty.read)
            except Exception:
                break
            if data:
                try:
                    await websocket.send_text(data)
                except Exception:
                    break
            else:
                # 没数据：检查 EOF，否则小睡避免 CPU 100%
                try:
                    if pty.iseof():
                        break
                except Exception:
                    break
                await asyncio.sleep(0.01)

    async def write_input():
        """从前端读输入 → 写入 PTY。支持 \x00 前缀的控制消息。"""
        try:
            while True:
                msg = await websocket.receive_text()
                if msg.startswith("\x00"):
                    # 控制消息
                    try:
                        ctrl = json.loads(msg[1:])
                        if ctrl.get("type") == "resize":
                            new_cols = int(ctrl.get("cols", 80))
                            new_rows = int(ctrl.get("rows", 24))
                            pty.set_size(new_cols, new_rows)
                        continue
                    except Exception:
                        pass
                # 普通 stdin
                pty.write(msg)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            # 🌟 WebSocket 断开 → 立即杀进程 + 通知 read_output 退出
            # 不放外层 finally，否则 gather 会死锁（read_output 等 iseof，杀进程在 finally）
            disconnected.set()
            if child_pid:
                _active_pids.discard(child_pid)
                _kill_pid_tree(child_pid)

    try:
        await asyncio.gather(read_output(), write_input())
    finally:
        try:
            pty.cancel_io()
        except Exception:
            pass


# ─────────────────────────────────────────────
# *nix: pty + os.fork 实现
# ─────────────────────────────────────────────
async def _serve_unix_pty(websocket: WebSocket, cmd: str | None):
    program, args = _build_spawn_unix(cmd)
    argv = [program] + args

    master_fd, slave_fd = _pty_module.openpty()

    pid = os.fork()
    if pid == 0:
        # 子进程
        os.close(master_fd)
        os.setsid()
        _pty_module.setraw(slave_fd)
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        os.close(slave_fd)
        try:
            os.execvp(program, argv)
        except Exception:
            os._exit(127)

    # 父进程
    os.close(slave_fd)
    _active_pids.add(pid)

    loop = asyncio.get_event_loop()
    disconnected = asyncio.Event()

    async def read_output():
        while True:
            if disconnected.is_set():
                break
            try:
                r, _, _ = await loop.run_in_executor(
                    None, lambda: select.select([master_fd], [], [], 0.05)
                )
                if not r:
                    # 检查子进程是否退出
                    done_pid, _ = os.waitpid(pid, os.WNOHANG)
                    if done_pid != 0:
                        break
                    continue
                data = os.read(master_fd, 4096)
                if not data:
                    break
                await websocket.send_text(data.decode("utf-8", errors="replace"))
            except (OSError, Exception):
                break

    async def write_input():
        try:
            while True:
                msg = await websocket.receive_text()
                if msg.startswith("\x00"):
                    try:
                        ctrl = json.loads(msg[1:])
                        if ctrl.get("type") == "resize":
                            winsize = struct.pack("HHHH",
                                                  int(ctrl.get("rows", 24)),
                                                  int(ctrl.get("cols", 80)),
                                                  0, 0)
                            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                        continue
                    except Exception:
                        pass
                os.write(master_fd, msg.encode("utf-8"))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            # WebSocket 断开 → 立即杀进程 + 通知 read_output 退出
            disconnected.set()
            _active_pids.discard(pid)
            _kill_pid_tree(pid)

    try:
        await asyncio.gather(read_output(), write_input())
    finally:
        try:
            os.close(master_fd)
        except Exception:
            pass
        try:
            os.waitpid(pid, os.WNOHANG)
        except Exception:
            pass


@router.websocket("/ws")
async def terminal_websocket(websocket: WebSocket, cmd: str | None = None):
    """
    WebSocket 终端桥接。

    query 参数:
        cmd: 可选。不传 → 启动交互 shell；传字符串 → 执行该命令（执行完保持可交互）。
    """
    await websocket.accept()

    try:
        if sys.platform.startswith("win"):
            await _serve_winpty(websocket, cmd)
        else:
            await _serve_unix_pty(websocket, cmd)
    except Exception as e:
        try:
            await websocket.send_text(f"\r\n\x1b[31m[Terminal Error] {e}\x1b[0m\r\n")
        except Exception:
            pass

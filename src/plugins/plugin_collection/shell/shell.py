import subprocess
import threading
import queue
import uuid
import time
import json
import os
import platform
import re
import getpass


class PersistentShellTool:
    MAX_OUTPUT_CHARS = 20000

    def __init__(self, timeout=60):
        self.is_windows = platform.system() == "Windows"
        self.timeout = timeout
        self.lock = threading.Lock()

        self._stop_event = threading.Event()
        self.process = None
        self.reader_thread = None
        self.output_queue = None

        self.username = getpass.getuser()
        self.hostname = platform.node() or "localhost"

        self.venv_name = ""
        if "VIRTUAL_ENV" in os.environ:
            self.venv_name = os.path.basename(os.environ["VIRTUAL_ENV"])
        elif "CONDA_DEFAULT_ENV" in os.environ:
            self.venv_name = os.environ["CONDA_DEFAULT_ENV"]
        self.venv_prefix = f"({self.venv_name}) " if self.venv_name else ""

        self._start_shell()

    def _start_shell(self):
        if self.process:
            self._stop_event.set()
            try:
                if self.process.stdin: self.process.stdin.close()
                self.process.kill()
                self.process.wait(timeout=1)
            except Exception:
                pass
            if self.reader_thread and self.reader_thread.is_alive():
                self.reader_thread.join(timeout=1)

        self._stop_event.clear()
        self.output_queue = queue.Queue()

        shell_cmd = (
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive"]
            if self.is_windows else ["/bin/bash"]
        )

        self.process = subprocess.Popen(
            shell_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
            encoding="utf-8", errors="replace"
        )

        if self.is_windows:
            init_cmd = "function prompt { '' }\n[Console]::OutputEncoding=[Text.UTF8Encoding]::UTF8\n"
        else:
            init_cmd = "export PS1=''\n"

        try:
            self.process.stdin.write(init_cmd)
            self.process.stdin.flush()
        except:
            pass

        self.reader_thread = threading.Thread(target=self._reader, args=(self.process.stdout, self._stop_event),
                                              daemon=True)
        self.reader_thread.start()

    def _reader(self, stdout_pipe, stop_event):
        try:
            for line in stdout_pipe:
                if stop_event.is_set(): break
                self.output_queue.put(line)
        except Exception:
            pass

    def _restart_shell_if_needed(self):
        if self.process.poll() is not None:
            self._start_shell()

    def _check_dangerous(self, command: str):
        patterns = [
            r"rm\s+-[A-Za-z]*r[A-Za-z]*f?[A-Za-z]*\s+(/|/\*|~|~/\*|\*)",
            r"del\s+/f\s+/s\s+/q",
            r"format\s+", r"mkfs", r"dd\s+.*of=/dev/", r">\s*/dev/sda",
            r"shutdown", r"reboot", r"poweroff", r"init\s+0",
            r":\(\)\{\s*:\|:&\s*\};:",
            r"^\s*(exit|kill|pkill|killall)\b"
        ]
        return any(re.search(p, command.lower()) for p in patterns)

    def _check_interactive(self, command: str):
        strict_int = r'(^|\||&&|;|sudo\s+)\s*(vim|nano|top|htop|ssh|less|more)\b'
        interp_int = r'(^|\||&&|;|sudo\s+)\s*(python|python3|node|bash|sh)\s*($|\||&&|;)'
        cmd = command.lower()
        return bool(re.search(strict_int, cmd) or bool(re.search(interp_int, cmd)))

    def run(self, command: str):
        if self._check_dangerous(command):
            return json.dumps({"type": "warning", "content": f"⚠️ 高危命令已拦截: {command}"}, ensure_ascii=False)
        if self._check_interactive(command):
            return json.dumps({"type": "error", "content": f"⚠️ 不支持交互式命令: {command}"}, ensure_ascii=False)

        with self.lock:
            self._restart_shell_if_needed()

            marker_id = uuid.uuid4().hex
            start_marker = f"__START_{marker_id}__"
            cwd_marker = f"__CWD_{marker_id}__"
            end_marker = f"__END_{marker_id}__"

            if self.is_windows:
                full_cmd = (
                    f"Write-Output '{start_marker}'\n"
                    f"{command}\n"
                    f"Write-Output '{cwd_marker}'\n"
                    f"(Get-Location).Path\n"
                    f"Write-Output '{end_marker}'\n"
                )
            else:
                full_cmd = (
                    f"echo '{start_marker}'\n"
                    f"{command}\n"
                    f"echo '{cwd_marker}'\n"
                    f"pwd\n"
                    f"echo '{end_marker}'\n"
                )

            ignore_echo_lines = {l.strip() for l in command.split('\n') if l.strip()}
            ignore_echo_lines.update({
                f"Write-Output '{cwd_marker}'", f"echo '{cwd_marker}'",
                "(Get-Location).Path", "pwd"
            })

            try:
                self.process.stdin.write(full_cmd)
                self.process.stdin.flush()
            except Exception as e:
                self._start_shell()
                return json.dumps({"type": "error", "content": f"Shell pipe write failed: {str(e)}"},
                                  ensure_ascii=False)
            state = "WAITING_START"
            output_lines = []
            cwd = "unknown"
            start_time = time.time()
            current_length = 0
            is_truncated = False

            while True:
                if time.time() - start_time > self.timeout:
                    self._start_shell()
                    return json.dumps(
                        {"type": "error", "content": f"⚠️ 命令执行超时 ({self.timeout}s)，后台 Shell 已强制重启清理。"},
                        ensure_ascii=False)

                try:
                    line = self.output_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                line_str = line.strip()

                if state == "WAITING_START":
                    if line_str == start_marker:
                        state = "READING_OUTPUT"
                    continue

                elif state == "READING_OUTPUT":
                    if line_str == cwd_marker:
                        state = "READING_CWD"
                        continue

                    if line_str in ignore_echo_lines or line_str.startswith(">> "):
                        continue

                    if not is_truncated:
                        output_lines.append(line)
                        current_length += len(line)
                        if current_length > self.MAX_OUTPUT_CHARS:
                            output_lines.append("\n\n...[Output truncated due to size limit]...\n")
                            is_truncated = True

                elif state == "READING_CWD":
                    if line_str == end_marker:
                        break
                    if line_str:
                        cwd = line_str
            final_lines = []
            for line in output_lines:
                line_str = line.strip()
                if (
                        "__AGENT_MARKER_" in line_str or
                        "__START_" in line_str or
                        "__END_" in line_str or
                        "__CWD_" in line_str or
                        "Write-Output" in line_str or
                        line_str.startswith("PS>") or
                        line_str == command.strip()
                ):
                    continue
                final_lines.append(line)

            cleaned_output = "".join(final_lines).strip()

            content = f"{cleaned_output}".strip()
            if not cleaned_output.strip():
                content += "\n(Command executed successfully with no output.)"

            return json.dumps({
                "type": "shell_output",
                "content": content
            }, ensure_ascii=False)

    def close(self):
        self._stop_event.set()
        if self.process:
            try:
                if self.process.stdin: self.process.stdin.close()
                if self.process.stdout: self.process.stdout.close()
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                try:
                    self.process.kill()
                except:
                    pass

# --- 插件导出接口 ---
_shell_instance = None


def run_command(command: str) -> str:
    from src.agent.agent import ROOT
    if not ROOT:
        return "未被赋予ROOT权限，无法使用shell工具！"
    global _shell_instance
    if _shell_instance is None:
        _shell_instance = PersistentShellTool()
    return _shell_instance.run(command)


def close_shell() -> str:
    global _shell_instance
    if _shell_instance is not None:
        _shell_instance.close()
        _shell_instance = None
        return json.dumps({"type": "info", "content": "Shell 会话已成功关闭。"}, ensure_ascii=False)
    return json.dumps({"type": "info", "content": "没有活跃的 Shell 会话。"}, ensure_ascii=False)



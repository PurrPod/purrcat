import json
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class ToolCallWidget(Vertical):
    def __init__(self, tool_name: str, arguments: dict):
        super().__init__()
        self.tool_name = tool_name
        self.arguments = arguments
        self._scanning = True
        self._scan_pos = 0
        self.scan_label = Static("  ⠋ 正在执行...", classes="tool-scanning")

    def compose(self) -> ComposeResult:
        args_str = json.dumps(self.arguments, ensure_ascii=False)
        # 禁用标记语言解析，避免代码内容被错误解析
        yield Static(f"{self.tool_name}({args_str})", classes="tool-header", markup=False)
        yield self.scan_label

    def on_mount(self):
        self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        if self._scanning:
            self._timer = self.set_interval(0.1, self._update_scan)

    def _update_scan(self):
        if self._scanning and self.is_mounted:  # 🟢 增加 is_mounted 保护
            self._scan_pos = (self._scan_pos + 1) % len(self._frames)
            try:
                self.scan_label.update(f"  {self._frames[self._scan_pos]} 正在执行...")
            except Exception:
                pass

    def finish(self, result: str):
        self._scanning = False
        if hasattr(self, "_timer"):
            self._timer.stop()

        snip = ""
        result_str = str(result)

        try:
            parsed = json.loads(result_str.strip())
            snip = parsed.get('snip', '') if isinstance(parsed, dict) else ''
        except (json.JSONDecodeError, Exception):
            snip = result_str.strip() if result_str.strip() else "执行完毕"

        if snip:
            self.scan_label.update(snip.replace("[", "\\[").replace("]", "\\]"))
        else:
            self.scan_label.update("执行完毕")

        self.scan_label.remove_class("tool-scanning")
        self.scan_label.add_class("tool-result")

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Markdown, Static


class ChatMessage(Vertical):
    def __init__(self, role: str, text: str, is_new: bool = False):
        super().__init__()
        self.role = role
        self.text = text
        self.is_new = is_new
        self.add_class(role)
        self._typing_timer = None
        self._current_text = ""
        self._target_text = text
        self._typing_index = 0

    def compose(self) -> ComposeResult:
        if self.role == "user":
            yield Static("> User", classes="role-user")
            yield Markdown(self.text)
        elif self.role == "assistant":
            yield Static("● PurrCat", classes="role-ai")
            if self.text and str(self.text).strip():
                self.md_widget = Markdown(self.text)
                yield self.md_widget
            else:
                self.md_widget = None

    def on_mount(self):
        if self.role == "assistant":
            if self.text == "" and self.is_new:
                if self.md_widget:
                    self.md_widget.update("⠋")
                    self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                    self._frame_index = 0
                    self._spinner_timer = self.set_interval(0.1, self._update_spinner)
            elif self.is_new and self.text and str(self.text).strip():
                self._start_typing()

    def _update_spinner(self):
        if hasattr(self, "md_widget") and self.is_mounted:
            try:
                self.md_widget.update(self._frames[self._frame_index])
                self._frame_index = (self._frame_index + 1) % len(self._frames)
            except Exception:
                pass

    def _start_typing(self):
        if hasattr(self, "_spinner_timer"):
            self._spinner_timer.stop()
        self._current_text = ""
        self._target_text = self.text
        self._typing_index = 0
        if self._typing_timer:
            self._typing_timer.stop()
        self._typing_timer = self.set_interval(0.015, self._type_next_char)

    def _type_next_char(self):
        chunk_size = 3
        if self._typing_index < len(self._target_text):
            self._current_text += self._target_text[
                self._typing_index : self._typing_index + chunk_size
            ]
            self._typing_index += chunk_size
            if hasattr(self, "md_widget"):
                self.md_widget.update(self._current_text)
        else:
            if self._typing_timer:
                self._typing_timer.stop()

    def update_content(self, new_text: str):
        if self.role == "assistant":
            self.text = new_text
            self._target_text = new_text
            if self._typing_timer:
                self._typing_timer.stop()
            if new_text and str(new_text).strip():
                if (
                    not hasattr(self, "md_widget")
                    or self.md_widget is None
                    or isinstance(self.md_widget, Static)
                ):
                    if hasattr(self, "md_widget") and self.md_widget:
                        self.md_widget.remove()
                    self.md_widget = Markdown(new_text)
                    self.mount(self.md_widget)
                self._start_typing()

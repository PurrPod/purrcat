import json
import time
from pathlib import Path

class Memory:
    def __init__(self, memory_base_dir="data/memory"):
        with open("data/config/config.json", "r") as f:
            config = json.load(f)
        self.memory_base_dir = Path(config.get("memory_base", memory_base_dir))
        self.date = time.strftime("%Y-%m-%d", time.localtime())
        self.month_str = "-".join(self.date.split("-")[:2]) if self.date else None  # 提取出 "2026-03"
        self._resolve_path()
    def _ensure_file_exists(self, file_path):
        if not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        if not file_path.exists():
            file_path.touch()
    def _resolve_path(self, date_str=None):
        target_date = date_str if date_str else self.date
        parts = target_date.split('-')
        if len(parts) >= 2:
            year_month = f"{parts[0]}-{parts[1]}"
            self.daily_path = self.memory_base_dir / year_month / target_date / "daily.jsonl"
            self.month_path = self.memory_base_dir / year_month / "monthly.jsonl"
        else:
            raise ValueError(f"无法解析的日期格式: {target_date}")
    def add(self, mem):
        line_to_write = json.dumps(mem, ensure_ascii=False) + "\n"
        if self.date:
            today_path = self.daily_path
            self._ensure_file_exists(today_path)
            with open(today_path, "a", encoding="utf8") as f:
                f.write(line_to_write)
        if self.month_str:
            month_path = self.month_path
            self._ensure_file_exists(month_path)
            with open(month_path, "a", encoding="utf8") as f:
                f.write(line_to_write)
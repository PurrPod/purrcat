import json
import time
from pathlib import Path
from src.utils.config import TRACKER_DIR

class Tracker:
    def __init__(self, tracker_base_dir=None):
        # 使用固定路径
        self.tracker_base_dir = Path(tracker_base_dir) if tracker_base_dir else Path(TRACKER_DIR)
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
            self.daily_path = self.tracker_base_dir / year_month / target_date / "daily.jsonl"
            self.month_path = self.tracker_base_dir / year_month / "monthly.jsonl"
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
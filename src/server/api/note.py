"""Note 按日归档接口（SPEC-032）。"""

from __future__ import annotations

import os
import re
from datetime import date as date_cls

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.server.api.common import unexpected_error
from src.utils.config import NOTES_DIR
from src.utils._fs import write_text

router = APIRouter(prefix="/api/note", tags=["Note"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class NoteWriteReq(BaseModel):
    date: str
    content: str = ""


def _note_path(value: str) -> str:
    if not _DATE_RE.match(value or ""):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    try:
        date_cls.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid date") from exc
    return os.path.join(NOTES_DIR, f"{value}.md")


@router.get("")
def read_note(date: str) -> dict:
    path = _note_path(date)
    try:
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
    except FileNotFoundError:
        content = ""
    except OSError as exc:
        raise unexpected_error("读取笔记失败", exc) from exc
    return {"date": date, "content": content, "path": path}


@router.put("")
def write_note(req: NoteWriteReq) -> dict:
    path = _note_path(req.date)
    try:
        if req.content.strip():
            write_text(path, req.content)
            return {"status": "success", "date": req.date, "deleted": False}
        if os.path.exists(path):
            os.remove(path)
        return {"status": "success", "date": req.date, "deleted": True}
    except OSError as exc:
        raise unexpected_error("保存笔记失败", exc) from exc


@router.get("/dates")
def list_dates() -> list[str]:
    try:
        names = os.listdir(NOTES_DIR)
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise unexpected_error("读取笔记归档失败", exc) from exc
    dates = [
        name[:-3]
        for name in names
        if name.endswith(".md") and _DATE_RE.match(name[:-3])
    ]
    return sorted(dates, reverse=True)

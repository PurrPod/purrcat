"""Note 按日归档 API（L1，SPEC-032）。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(router):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _note_client(monkeypatch, tmp_path):
    from src.server.api import note

    monkeypatch.setattr(note, "NOTES_DIR", str(tmp_path))
    return _client(note.router), tmp_path


def test_missing_note_returns_empty(monkeypatch, tmp_path) -> None:
    """SPEC-032：当天没有内容时返回空串，不落盘。"""
    client, _ = _note_client(monkeypatch, tmp_path)

    resp = client.get("/api/note", params={"date": "2026-01-01"})

    assert resp.status_code == 200
    assert resp.json() == {
        "date": "2026-01-01",
        "content": "",
        "path": str(tmp_path / "2026-01-01.md"),
    }
    assert list(tmp_path.iterdir()) == []


def test_write_read_and_dates(monkeypatch, tmp_path) -> None:
    """SPEC-032：内容按日期归档，空白时删除文件。"""
    client, root = _note_client(monkeypatch, tmp_path)

    saved = client.put(
        "/api/note", json={"date": "2026-01-02", "content": "# 今天\n写点东西"}
    )
    assert saved.status_code == 200
    assert saved.json()["deleted"] is False
    assert (root / "2026-01-02.md").read_text(encoding="utf-8") == "# 今天\n写点东西"

    client.put("/api/note", json={"date": "2026-01-01", "content": "旧的一天"})
    assert client.get("/api/note/dates").json() == ["2026-01-02", "2026-01-01"]
    assert client.get("/api/note", params={"date": "2026-01-02"}).json() == {
        "date": "2026-01-02",
        "content": "# 今天\n写点东西",
        "path": str(root / "2026-01-02.md"),
    }

    cleared = client.put("/api/note", json={"date": "2026-01-02", "content": "  \n"})
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] is True
    assert not (root / "2026-01-02.md").exists()
    assert client.get("/api/note/dates").json() == ["2026-01-01"]


def test_invalid_date_rejected(monkeypatch, tmp_path) -> None:
    """SPEC-032：日期必须是 YYYY-MM-DD，防止路径穿越。"""
    client, _ = _note_client(monkeypatch, tmp_path)

    assert client.get("/api/note", params={"date": "../evil"}).status_code == 400
    assert (
        client.put("/api/note", json={"date": "2026-13-01", "content": "x"}).status_code
        == 400
    )

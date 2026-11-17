"""定时任务 HTTP 契约（L1，SPEC-034 AC-6）。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.timer.service import TimerService


def _client(router):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_timer_event_crud_contract(monkeypatch, tmp_path) -> None:
    """SPEC-034 AC-6：events / sources / state / delete 契约。"""
    from src.server.api import timer as timer_api

    svc = TimerService(store_path=str(tmp_path / "timer.json"), sinks={})
    monkeypatch.setattr(timer_api, "get_timer_service", lambda: svc)
    client = _client(timer_api.router)

    created = client.post(
        "/api/timer/events",
        json={
            "id": "e1",
            "source": "demo",
            "target": "main",
            "at": 1000.0,
            "effect": {"signal": "ping"},
        },
    )
    assert created.status_code == 200
    assert created.json()["id"] == "e1"

    listed = client.get("/api/timer/events", params={"source": "demo"}).json()
    assert [e["id"] for e in listed] == ["e1"]

    replaced = client.put(
        "/api/timer/sources/note:2026-01-01",
        json={
            "events": [
                {"id": "n1", "target": "main", "at": 2000.0, "effect": {}},
                {"id": "n2", "target": "graph:daily", "at": 3000.0, "effect": {}},
            ]
        },
    )
    assert replaced.status_code == 200
    assert sorted(e["id"] for e in replaced.json()) == ["n1", "n2"]

    # source 以路径参数为准，覆盖请求体中的同名字段
    assert all(e["source"] == "note:2026-01-01" for e in replaced.json())

    state = client.get("/api/timer/state").json()
    assert state["pending"] == 3
    assert state["next_at"] == 1000.0

    assert client.delete("/api/timer/events/e1").status_code == 200
    assert client.delete("/api/timer/events/missing").status_code == 404
    assert [e["id"] for e in client.get("/api/timer/events").json()] == ["n1", "n2"]

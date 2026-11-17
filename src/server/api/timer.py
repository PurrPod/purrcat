"""定时任务中心 HTTP 接口（SPEC-034）。"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.timer import get_timer_service

router = APIRouter(prefix="/api/timer", tags=["Timer"])

_SSE_KEEPALIVE = 15.0


class TimerEventReq(BaseModel):
    id: str | None = None
    source: str | None = None
    target: str
    at: float
    effect: dict = Field(default_factory=dict)
    repeat: dict | None = None
    catch_up: str = "skip"
    dedupe_key: str | None = None


class SourceEventsReq(BaseModel):
    events: list[TimerEventReq] = Field(default_factory=list)


@router.post("/events")
def create_event(req: TimerEventReq) -> dict:
    if not req.source:
        raise HTTPException(status_code=400, detail="source is required")
    try:
        event = get_timer_service().add_event(req.model_dump())
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return event.to_dict()


@router.put("/sources/{source}")
def replace_source(source: str, req: SourceEventsReq) -> list[dict]:
    events = []
    for item in req.events:
        data = item.model_dump()
        data.pop("source", None)
        events.append(data)
    try:
        result = get_timer_service().replace_source(source, events)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [event.to_dict() for event in result]


@router.get("/events")
def list_events(
    source: str | None = None, include_finished: bool = False
) -> list[dict]:
    events = get_timer_service().list_events(source)
    if include_finished:
        return events
    return [event for event in events if event["status"] == "pending"]


@router.delete("/events/{event_id}")
def delete_event(event_id: str) -> dict:
    if not get_timer_service().cancel(event_id):
        raise HTTPException(status_code=404, detail="timer event not found")
    return {"status": "success", "id": event_id}


@router.get("/state")
def timer_state() -> dict:
    return get_timer_service().state()


@router.get("/stream")
async def timer_stream() -> StreamingResponse:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=256)

    def _put(payload: dict) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass

    unsubscribe = get_timer_service().subscribe(_put, loop)

    async def _gen():
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(
                        queue.get(), timeout=_SSE_KEEPALIVE
                    )
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: timer\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            unsubscribe()

    return StreamingResponse(_gen(), media_type="text/event-stream")

"""
PurrMemo client wrapper for purrcat.

Robustly integrates PurrMemo memory system:
- Falls back to local memory.md if PurrMemo server is unreachable
- Thread-safe with timeout protection
- Config-driven enable/disable via config.yaml
"""

import os
import json
import threading
import requests
from typing import Optional

# Module-level state
_client = None
_client_lock = threading.Lock()
_client_available = False


def get_purrmemo_config() -> dict:
    """Get PurrMemo configuration from sensor config."""
    from src.utils.config import get_sensor_config
    return get_sensor_config().get("purrmemo", {})


def is_enabled() -> bool:
    """Check if PurrMemo integration is enabled in config."""
    cfg = get_purrmemo_config()
    return cfg.get("enabled", False)


def _get_client():
    """Get or create PurrMemo HTTP client (thread-safe, cached)."""
    global _client, _client_available
    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client

        cfg = get_purrmemo_config()
        host = cfg.get("host", "http://127.0.0.1:8000")
        api_key = cfg.get("api_key")

        try:
            import requests as req
            session = req.Session()
            session.trust_env = False
            session.timeout = (3, 10)  # connect timeout 3s, read timeout 10s

            # Quick health check
            resp = session.get(f"{host.rstrip('/')}/api/v1/health", timeout=3)
            body = resp.json()
            if body.get("status") != "ok":
                raise ConnectionError(f"PurrMemo health check failed: {body}")

            _client = {
                "session": session,
                "host": host.rstrip("/"),
                "api_key": api_key,
            }
            _client_available = True
            print("[PurrMemo] Connected to PurrMemo server at", host)
        except Exception as e:
            _client = None
            _client_available = False
            print(f"[PurrMemo] Server unreachable at {host}: {e}")
            print("[PurrMemo] Falling back to local memory.md")

        return _client


def push_memo(
    events: list = None,
    work_exp: list = None,
    cognition: list = None,
    reminders: str = None,
    project_state: str = None,
) -> bool:
    """
    Push memory to PurrMemo. Maps update_memo fields to PurrMemo's push API.

    - events: list of {time, event} dicts
    - work_exp: list of work experience strings
    - cognition: list of cognition/decision strings

    Returns True if successfully pushed to PurrMemo, False if fell back.
    """
    client = _get_client()
    if client is None:
        return False

    import datetime
    now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

    # Events already validated as {time, event} dicts
    formatted_events = list(events) if events else []
    if reminders:
        formatted_events.append({"time": now, "event": f"[reminder] {reminders[:500]}"})
    if project_state:
        formatted_events.append({"time": now, "event": f"[project] {project_state[:500]}"})

    payload = {
        "events": formatted_events,
        "work_exp": [w.strip()[:1000] for w in (work_exp or []) if w and w.strip()],
        "cognition": [c.strip()[:1000] for c in (cognition or []) if c and c.strip()],
        "timestamp": now,
        "source": "main_agent",
    }

    try:
        resp = client["session"].post(
            f"{client['host']}/api/v1/push",
            json=payload,
            timeout=10,
        )
        body = resp.json()
        if body.get("status") == "ok":
            print(f"[PurrMemo] Memory pushed: {body.get('message', '')}")
            return True
        else:
            print(f"[PurrMemo] Push returned: {body}")
            return False
    except requests.Timeout:
        print("[PurrMemo] Push timed out")
        return False
    except Exception as e:
        print(f"[PurrMemo] Push error: {e}")
        return False


def search_memo(query: str, time_range: tuple = None, threshold: float = None) -> Optional[str]:
    """
    Search PurrMemo for relevant memories.

    Args:
        query: Search query text
        time_range: Optional (start, end) tuple like ("2026-04-01", "2026-04-27")
        threshold: Optional semantic similarity threshold (0.0~1.0)

    Returns context string from PurrMemo, or None if unavailable.
    """
    client = _get_client()
    if client is None:
        return None

    try:
        params = {"query": query}
        filters = {}
        if time_range:
            filters["time_range"] = list(time_range)
        if threshold is not None:
            filters["threshold"] = threshold
        if filters:
            params["filters"] = json.dumps(filters)

        resp = client["session"].get(
            f"{client['host']}/api/v1/search",
            params=params,
            timeout=10,
        )
        body = resp.json()
        if body.get("status") == "ok":
            return body.get("context", "")
        return None
    except Exception:
        return None


def check_health() -> dict:
    """Check PurrMemo server health status."""
    client = _get_client()
    if client is None:
        return {"status": "unavailable", "message": "PurrMemo not connected"}

    try:
        resp = client["session"].get(
            f"{client['host']}/api/v1/health",
            timeout=3,
        )
        if resp.status_code == 200:
            return resp.json()
        return {"status": "error", "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def invalidate_client():
    """Force reconnect on next call. Call this if config changes."""
    global _client, _client_available
    with _client_lock:
        _client = None
        _client_available = False

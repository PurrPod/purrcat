"""配置中心沙盒挂载 API（SPEC-045）。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.api import config as config_api
from src.server.api import config_services
from src.utils import sandbox_mounts as sm


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "MOUNTS_CONFIG_PATH", str(tmp_path / "mounts.json"))
    monkeypatch.setattr(
        config_services, "_inspect_sandbox_mounts", lambda: (False, False, {})
    )
    app = FastAPI()
    app.include_router(config_api.router)
    return TestClient(app)


def test_mount_crud_flow(client, tmp_path):
    source = tmp_path / "proj"
    source.mkdir()

    created = client.post("/api/config/mounts", json={"source": str(source)})
    assert created.status_code == 200
    assert created.json()["mount"]["name"] == "proj"

    listed = client.get("/api/config/mounts")
    body = listed.json()
    assert body["docker_ok"] is False
    assert [m["name"] for m in body["mounts"]] == ["proj"]
    assert body["mounts"][0]["status"] == "pending"

    renamed = client.put("/api/config/mounts/proj", json={"name": "renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["mount"]["name"] == "renamed"

    deleted = client.delete("/api/config/mounts/renamed")
    assert deleted.status_code == 200
    assert client.get("/api/config/mounts").json()["mounts"] == []


def test_mount_add_rejects_missing_directory(client, tmp_path):
    response = client.post(
        "/api/config/mounts", json={"source": str(tmp_path / "missing")}
    )

    assert response.status_code == 400


def test_mount_rename_rejects_taken_name(client, tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    assert (
        client.post("/api/config/mounts", json={"source": str(first)}).status_code
        == 200
    )
    assert (
        client.post("/api/config/mounts", json={"source": str(second)}).status_code
        == 200
    )

    response = client.put("/api/config/mounts/a", json={"name": "b"})

    assert response.status_code == 400

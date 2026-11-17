"""默认 PARADIGM 模板单一来源与恢复默认接口（SPEC-038）。"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.api import paradigms
from src.utils import initial, initial_templates, paradigm_api


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(paradigms.router)
    return TestClient(app)


def test_default_paradigm_template_is_single_repo_file() -> None:
    """SPEC-038：模板只保留 system_rules 一份，播种与兜底都读它。"""
    source = Path(initial_templates.PARADIGM_TEMPLATE_PATH).read_text(encoding="utf-8")

    assert initial_templates.DEFAULT_PARADIGM_YAML == source
    assert "exist_check" not in source


def test_reset_paradigm_restores_template(tmp_path, monkeypatch) -> None:
    """SPEC-038：恢复默认只覆盖 PARADIGM.yaml，其它自定义 loop 保留。"""
    monkeypatch.setattr(paradigm_api, "PARADIGMS_DIR", str(tmp_path))
    target = tmp_path / "PARADIGM.yaml"
    target.write_text("name: custom\n", encoding="utf-8")
    other = tmp_path / "coding.yaml"
    other.write_text("name: coding\n", encoding="utf-8")

    resp = _client().post("/api/paradigms/reset")

    assert resp.status_code == 200
    assert resp.json()["name"] == "PARADIGM"
    assert target.read_text(encoding="utf-8") == initial.DEFAULT_PARADIGM_YAML
    assert other.read_text(encoding="utf-8") == "name: coding\n"

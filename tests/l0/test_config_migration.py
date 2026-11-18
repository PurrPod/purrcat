"""托管配置文件的版本检测与自动迁移（缺失/旧版/损坏/新版本）。"""

from __future__ import annotations

import json
import os

from src.utils import config_migration as cm


def _spec(tmp_path, deprecated=(), required=("a",), template=None):
    path = tmp_path / "cfg.json"
    spec = cm.ConfigSpec(
        "demo",
        str(path),
        lambda: dict(template or {"a": 1}),
        deprecated=deprecated,
        required=required,
    )
    return spec, path


def test_managed_configs_cover_all_managed_files():
    keys = {spec.key for spec in cm.managed_configs()}

    assert {"model", "sensor", "file", "mcp", "memory", "settings"} <= keys


def test_missing_file_is_created_with_latest_version(tmp_path):
    spec, path = _spec(tmp_path)

    report = cm.migrate_configs([spec], backup_dir=str(tmp_path / "backups"))

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "_version": 1}
    assert report["files"][0]["action"] == "created"
    assert report["changed"] == 1
    assert report["backup_dir"] is None  # 新建文件没有旧内容需要备份


def test_legacy_file_drops_deprecated_keeps_unknown_fields(tmp_path):
    spec, path = _spec(tmp_path, deprecated=("old",))
    path.write_text(json.dumps({"a": 1, "old": 2, "custom": "keep"}), encoding="utf-8")

    report = cm.migrate_configs([spec], backup_dir=str(tmp_path / "backups"))

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"a": 1, "custom": "keep", "_version": 1}
    assert report["files"][0]["removed"] == ["old"]
    backup = report["files"][0]["backup"]
    assert backup and json.loads(open(backup, encoding="utf-8").read())["old"] == 2


def test_missing_required_field_is_filled_from_template(tmp_path):
    spec, path = _spec(tmp_path, template={"a": 1, "b": 2})
    path.write_text(json.dumps({"b": 9}), encoding="utf-8")

    cm.migrate_configs([spec], backup_dir=str(tmp_path / "backups"))

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["a"] == 1
    assert data["b"] == 9  # 已有字段不被模板覆盖
    assert data["_version"] == 1


def test_up_to_date_file_is_not_rewritten(tmp_path):
    spec, path = _spec(tmp_path)
    path.write_text(json.dumps({"a": 1, "_version": 1}), encoding="utf-8")
    before = os.stat(path).st_mtime_ns

    report = cm.migrate_configs([spec], backup_dir=str(tmp_path / "backups"))

    assert os.stat(path).st_mtime_ns == before
    assert report["changed"] == 0
    assert report["files"][0]["action"] == "ok"
    assert not os.path.exists(str(tmp_path / "backups"))


def test_corrupt_file_is_backed_up_and_rebuilt(tmp_path):
    spec, path = _spec(tmp_path)
    path.write_text("{not json", encoding="utf-8")

    report = cm.migrate_configs([spec], backup_dir=str(tmp_path / "backups"))

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "_version": 1}
    assert report["files"][0]["action"] == "recreated"
    assert report["files"][0]["backup"]
    assert list(tmp_path.glob("cfg.json.corrupt-*"))


def test_newer_version_is_reported_but_not_downgraded(tmp_path):
    spec, path = _spec(tmp_path, deprecated=("old",))
    original = {"a": 1, "old": 2, "_version": 99}
    path.write_text(json.dumps(original), encoding="utf-8")

    report = cm.migrate_configs([spec], backup_dir=str(tmp_path / "backups"))

    assert json.loads(path.read_text(encoding="utf-8")) == original
    assert report["files"][0]["action"] == "skipped_newer"
    assert cm.inspect_config(spec)["status"] == "newer"


def test_migrate_is_idempotent(tmp_path):
    spec, path = _spec(tmp_path, deprecated=("old",))
    path.write_text(json.dumps({"a": 1, "old": 2}), encoding="utf-8")
    backups = str(tmp_path / "backups")

    first = cm.migrate_configs([spec], backup_dir=backups)
    second = cm.migrate_configs([spec], backup_dir=backups)

    assert first["changed"] == 1
    assert second["changed"] == 0


def test_inspect_reports_statuses(tmp_path):
    spec, path = _spec(tmp_path)
    assert cm.inspect_config(spec)["status"] == "missing"

    path.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert cm.inspect_config(spec)["status"] == "legacy"

    path.write_text(json.dumps({"a": 1, "old": 2, "_version": 1}), encoding="utf-8")
    spec_old = cm.ConfigSpec("demo", str(path), lambda: {"a": 1}, deprecated=("old",), required=("a",))
    assert cm.inspect_config(spec_old)["status"] == "outdated"

    report = cm.inspect_configs([spec])
    assert report["ok"] is True


def test_apply_version_only_for_managed_paths(tmp_path):
    spec, path = _spec(tmp_path)
    path.write_text(json.dumps({"a": 1, "_version": 5}), encoding="utf-8")

    assert cm.apply_version(str(path), {"a": 2}, [spec])["_version"] == 5
    assert cm.apply_version(str(tmp_path / "other.json"), {"a": 2}) == {"a": 2}


def test_apply_version_injects_latest_when_missing(tmp_path):
    spec, path = _spec(tmp_path)
    path.write_text(json.dumps({"a": 1}), encoding="utf-8")

    assert cm.apply_version(str(path), {"a": 1}, [spec])["_version"] == 1

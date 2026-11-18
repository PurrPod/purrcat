"""托管配置文件的版本化、结构检测与自动迁移。

启动时由 ``initial.ensure_initialized()`` 调用 ``migrate_configs()``：

- 缺失文件：用内置模板补齐（并写入 ``_version``）
- 损坏文件：先备份并从模板重建（原文件改名为 ``*.corrupt-<ts>`` 留档）
- 旧版本：删除已废弃字段、补齐必需字段、写入最新 ``_version``；未知字段一律保留
- 版本高于当前程序：只报告，不降级改写
- 已是最新：不写盘（幂等）

检测（``inspect_configs``）与迁移（``migrate_configs``）都按文件逐个进行，
每次改写前把原文件复制到 ``~/.purrcat/backups/config-<ts>/``，失败不影响原文件。
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

from src.utils import initial_templates
from src.utils._fs import write_json_atomic
from src.utils.config import (
    CONFIG_VERSION_KEY,
    FILE_CONFIG_PATH,
    GLOBAL_CONFIG_FILE,
    LATEST_CONFIG_VERSION,
    MCP_CONFIG_PATH,
    MODEL_CONFIG_PATH,
    PURRCAT_DIR,
    SENSOR_CONFIG_PATH,
)

LATEST_VERSION = LATEST_CONFIG_VERSION
BACKUP_DIR = os.path.join(PURRCAT_DIR, "backups")


@dataclass(frozen=True)
class ConfigSpec:
    """一个受管配置文件的检测/迁移规则。"""

    key: str
    path: str
    template: Callable[[], dict]
    deprecated: Tuple[str, ...] = ()
    required: Tuple[str, ...] = ()


def _memory_spec() -> ConfigSpec:
    # 延迟导入：memory.settings 依赖 src.utils.config，避免模块级循环引用
    from src.memory.settings import DEFAULT_KEYS, DEPRECATED_KEYS, MEMORY_CONFIG_PATH

    defaults = _memory_defaults()
    return ConfigSpec(
        key="memory",
        path=MEMORY_CONFIG_PATH,
        template=lambda: dict(defaults),
        deprecated=DEPRECATED_KEYS,
        required=DEFAULT_KEYS,
    )


def _memory_defaults() -> Dict[str, Any]:
    from src.memory.settings import DEFAULTS

    return dict(DEFAULTS)


def managed_configs() -> List[ConfigSpec]:
    """当前程序托管、需要版本化与结构检测的配置文件。"""
    return [
        ConfigSpec(
            "model",
            MODEL_CONFIG_PATH,
            initial_templates.model_config_dict,
            required=("main", "task", "vision"),
        ),
        ConfigSpec(
            "sensor",
            SENSOR_CONFIG_PATH,
            initial_templates.sensor_config_dict,
        ),
        ConfigSpec(
            "file",
            FILE_CONFIG_PATH,
            initial_templates.file_config_dict,
            required=("default_permission", "permissions"),
        ),
        ConfigSpec(
            "mcp",
            MCP_CONFIG_PATH,
            initial_templates.mcp_config_dict,
            required=("mcpServers",),
        ),
        _memory_spec(),
        ConfigSpec("settings", str(GLOBAL_CONFIG_FILE), dict),
    ]


def _norm(path: Any) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def find_spec(path: Any, configs: List[ConfigSpec] | None = None) -> ConfigSpec | None:
    target = _norm(path)
    for spec in configs if configs is not None else managed_configs():
        if _norm(spec.path) == target:
            return spec
    return None


def read_version(path: Any) -> int | None:
    """读取文件中的 ``_version``；缺失/损坏/非整数一律返回 None。"""
    try:
        with open(str(path), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get(CONFIG_VERSION_KEY)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def apply_version(path: Any, data: Any, configs: List[ConfigSpec] | None = None) -> Any:
    """写盘前补 ``_version``：只升不降，非托管文件原样返回。"""
    if not isinstance(data, dict) or find_spec(path, configs) is None:
        return data
    existing = read_version(path)
    version = LATEST_VERSION if existing is None else max(existing, LATEST_VERSION)
    if data.get(CONFIG_VERSION_KEY) == version:
        return data
    result = dict(data)
    result[CONFIG_VERSION_KEY] = version
    return result


def _read_json(path: str) -> Tuple[Any, str | None]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError) as e:
        return None, str(e)


def inspect_config(spec: ConfigSpec) -> Dict[str, Any]:
    """只读检测单个文件：存在性、版本、废弃字段与必需字段。"""
    entry = {
        "key": spec.key,
        "path": spec.path,
        "exists": os.path.exists(spec.path),
        "version": None,
        "latest": LATEST_VERSION,
        "status": "missing",
        "deprecated": [],
        "missing_fields": [],
    }
    if not entry["exists"]:
        return entry

    data, error = _read_json(spec.path)
    if error:
        entry["status"] = "corrupt"
        entry["error"] = error
        return entry
    if not isinstance(data, dict):
        entry["status"] = "invalid"
        return entry

    version = data.get(CONFIG_VERSION_KEY)
    if not isinstance(version, bool) and isinstance(version, int):
        entry["version"] = version
    entry["deprecated"] = [key for key in spec.deprecated if key in data]
    entry["missing_fields"] = [key for key in spec.required if key not in data]

    if entry["version"] is None:
        entry["status"] = "legacy"
    elif entry["version"] > LATEST_VERSION:
        entry["status"] = "newer"
    elif entry["deprecated"] or entry["missing_fields"] or entry["version"] < LATEST_VERSION:
        entry["status"] = "outdated"
    else:
        entry["status"] = "ok"
    return entry


def inspect_configs(configs: List[ConfigSpec] | None = None) -> Dict[str, Any]:
    """逐文件检测全部托管配置，返回报告与问题清单（不写盘）。"""
    files = [inspect_config(spec) for spec in (configs or managed_configs())]
    issues = []
    for entry in files:
        status = entry["status"]
        if status == "ok":
            continue
        level = "warn" if status != "missing" else "error"
        issues.append(
            {
                "code": f"config_{entry['key']}_{status}",
                "level": level,
                "file": entry["path"],
                "status": status,
                "message": _status_message(entry),
            }
        )
    return {
        "latest_version": LATEST_VERSION,
        "files": files,
        "issues": issues,
        "ok": not issues,
    }


def _status_message(entry: Dict[str, Any]) -> str:
    name = os.path.basename(entry["path"])
    status = entry["status"]
    if status == "missing":
        return f"{name} 缺失，将自动生成默认配置"
    if status == "corrupt":
        return f"{name} 已损坏，将备份后重建"
    if status == "invalid":
        return f"{name} 顶层不是 JSON 对象，将备份后重建"
    if status == "legacy":
        return f"{name} 为旧版本（无版本号），将自动迁移"
    if status == "newer":
        return f"{name} 版本 {entry['version']} 高于当前程序（{LATEST_VERSION}），已保留不改写"
    return f"{name} 需要更新（版本 {entry['version']} → {LATEST_VERSION}）"


def _new_backup_dir(root: str) -> str:
    path = os.path.join(root, time.strftime("config-%Y%m%d-%H%M%S"))
    os.makedirs(path, exist_ok=True)
    return path


def _backup(path: str, backup_dir: str) -> str | None:
    try:
        target = os.path.join(backup_dir, os.path.basename(path))
        if os.path.exists(target):
            stem, ext = os.path.splitext(target)
            target = f"{stem}-{time.strftime('%H%M%S')}{ext}"
        shutil.copy2(path, target)
        return target
    except OSError as e:
        print(f"[Config] 备份失败 {path}: {e}")
        return None


def _write(path: str, data: dict) -> None:
    write_json_atomic(path, data)


def migrate_configs(
    configs: List[ConfigSpec] | None = None, backup_dir: str | None = None
) -> Dict[str, Any]:
    """让全部托管配置达到最新结构；返回每个文件处理结果。

    幂等：已是最新的文件不会重写，也不会产生备份。
    """
    specs = configs or managed_configs()
    root = backup_dir or BACKUP_DIR
    backup_path = None
    changed = 0
    results = []

    for spec in specs:
        item = {
            "key": spec.key,
            "path": spec.path,
            "action": "ok",
            "removed": [],
            "added": [],
            "backup": None,
            "error": None,
        }
        try:
            data, error = _read_json(spec.path)
            exists = os.path.exists(spec.path)

            if exists and error is None and not isinstance(data, dict):
                error = "not-object"

            if not exists or error:
                if exists:
                    backup_path = backup_path or _new_backup_dir(root)
                    item["backup"] = _backup(spec.path, backup_path)
                    try:
                        os.replace(spec.path, f"{spec.path}.corrupt-{int(time.time())}")
                    except OSError as e:
                        print(f"[Config] 损坏文件留档失败 {spec.path}: {e}")
                new = dict(spec.template())
                new[CONFIG_VERSION_KEY] = LATEST_VERSION
                _write(spec.path, new)
                item["action"] = "recreated" if exists else "created"
                changed += 1
                results.append(item)
                continue

            version = data.get(CONFIG_VERSION_KEY)
            if isinstance(version, int) and not isinstance(version, bool) and version > LATEST_VERSION:
                item["action"] = "skipped_newer"
                results.append(item)
                continue

            new = dict(data)
            item["removed"] = [key for key in spec.deprecated if key in new]
            for key in item["removed"]:
                new.pop(key, None)

            template = spec.template()
            item["added"] = [key for key in spec.required if key not in new]
            for key in item["added"]:
                new[key] = template.get(key)
            new[CONFIG_VERSION_KEY] = LATEST_VERSION

            if new != data:
                only_version = (
                    not item["removed"]
                    and not item["added"]
                    and {k: v for k, v in data.items() if k != CONFIG_VERSION_KEY}
                    == {k: v for k, v in new.items() if k != CONFIG_VERSION_KEY}
                )
                if not only_version:
                    # 只有版本号缺失时不备份，避免每次启动产生无意义备份
                    backup_path = backup_path or _new_backup_dir(root)
                    item["backup"] = _backup(spec.path, backup_path)
                    item["action"] = "migrated"
                else:
                    item["action"] = "stamped"
                _write(spec.path, new)
                changed += 1
        except Exception as e:  # 单文件失败不影响其它文件
            item["error"] = str(e)
            item["action"] = "failed"
            print(f"[Config] 迁移失败 {spec.path}: {e}")
        results.append(item)

    return {
        "latest_version": LATEST_VERSION,
        "backup_dir": backup_path,
        "changed": changed,
        "files": results,
    }

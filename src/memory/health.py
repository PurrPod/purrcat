"""记忆系统健康检测与自动迁移。

覆盖四类对象：

- ``~/.purrcat/memory.json``：配置版本 / 废弃字段 / 缺失字段
- ``experiences.db`` / ``events.db``：结构版本、必需表、FTS 行数一致性
- Chroma 向量库：三个 collection 是否齐全
- 图谱与缓冲目录：仅作为状态展示，不影响健康判定

启动时由 ``run_startup_check()`` 调用：先只读检测，有问题就自动迁移（改写前
备份），迁移后仍有未修复问题时只打印日志；也可以调用接口手动查看或触发迁移。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from src.memory import config as memory_config
from src.utils.config import MEMORY_DIR

MEMORY_SCHEMA_VERSION = 2

_EXPERIENCE_TABLES = (
    "experiences",
    "experiences_fts",
    "experience_events",
    "index_outbox",
    "schema_meta",
)


# ==========================================
# 路径与只读连接
# ==========================================


def _default_paths() -> Dict[str, Any]:
    from src.memory.settings import MEMORY_CONFIG_PATH

    return {
        "memory_json": MEMORY_CONFIG_PATH,
        "experiences_db": memory_config.EXPERIENCES_DB_PATH,
        "events_db": memory_config.EVENTDB_PATH,
        "events_table": memory_config.EVENTDB_TABLE_NAME,
        "chroma_dir": memory_config.CHROMADB_PERSIST_DIRECTORY,
        "graph": memory_config.GRAPHDB_PATH,
        "buffer": os.path.join(MEMORY_DIR, "buffer"),
    }


def _paths(overrides: Dict[str, Any] | None) -> Dict[str, Any]:
    result = _default_paths()
    if overrides:
        result.update(overrides)
    return result


def _open_ro(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn: sqlite3.Connection) -> set:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
    ).fetchall()
    return {row[0] for row in rows}


def _count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.Error:
        return 0


def _schema_version(conn: sqlite3.Connection) -> int | None:
    try:
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


# ==========================================
# 只读检测
# ==========================================


def _inspect_experiences(path: str) -> Dict[str, Any]:
    info = {
        "path": path,
        "exists": os.path.exists(path),
        "schema_version": None,
        "missing_tables": [],
        "rows": 0,
        "fts_rows": 0,
        "fts_in_sync": True,
    }
    if not info["exists"]:
        return info
    conn = _open_ro(path)
    try:
        tables = _tables(conn)
        info["missing_tables"] = [t for t in _EXPERIENCE_TABLES if t not in tables]
        info["schema_version"] = _schema_version(conn)
        if "experiences" in tables:
            info["rows"] = _count(conn, "experiences")
        if "experiences_fts" in tables:
            info["fts_rows"] = _count(conn, "experiences_fts")
        info["fts_in_sync"] = info["rows"] == info["fts_rows"]
    except sqlite3.Error as e:
        info["error"] = str(e)
    finally:
        conn.close()
    return info


def _inspect_events(path: str, table: str) -> Dict[str, Any]:
    info = {
        "path": path,
        "exists": os.path.exists(path),
        "schema_version": None,
        "missing_tables": [],
        "rows": 0,
        "fts_rows": 0,
        "fts_in_sync": True,
    }
    if not info["exists"]:
        return info
    expected = (table, f"{table}_fts", "index_outbox", "schema_meta")
    conn = _open_ro(path)
    try:
        tables = _tables(conn)
        info["missing_tables"] = [t for t in expected if t not in tables]
        info["schema_version"] = _schema_version(conn)
        if table in tables:
            info["rows"] = _count(conn, table)
        if f"{table}_fts" in tables:
            info["fts_rows"] = _count(conn, f"{table}_fts")
        info["fts_in_sync"] = info["rows"] == info["fts_rows"]
    except sqlite3.Error as e:
        info["error"] = str(e)
    finally:
        conn.close()
    return info


def _inspect_chroma(directory: str) -> Dict[str, Any]:
    path = os.path.join(directory, "chroma.sqlite3")
    info = {
        "path": path,
        "exists": os.path.exists(path),
        "collections": [],
        "missing": [],
        "readable": True,
    }
    if not info["exists"]:
        return info
    expected = [
        memory_config.CHROMADB_EVENTS_COLLECTION_NAME,
        memory_config.CHROMADB_COLLECTION_NAME,
        memory_config.CHROMADB_GRAPH_COLLECTION_NAME,
    ]
    conn = _open_ro(path)
    try:
        info["collections"] = [
            row[0] for row in conn.execute("SELECT name FROM collections").fetchall()
        ]
        info["missing"] = [name for name in expected if name not in info["collections"]]
    except sqlite3.Error:
        # 旧版 Chroma 表结构可能不同，读不到时不误报
        info["readable"] = False
    finally:
        conn.close()
    return info


def _inspect_memory_config(path: str) -> Dict[str, Any]:
    from src.memory.settings import DEFAULTS, DEFAULT_KEYS, DEPRECATED_KEYS
    from src.utils.config_migration import ConfigSpec, inspect_config

    spec = ConfigSpec(
        "memory",
        path,
        lambda: dict(DEFAULTS),
        deprecated=DEPRECATED_KEYS,
        required=DEFAULT_KEYS,
    )
    return inspect_config(spec)


def _buffer_stats(directory: str) -> Dict[str, int]:
    stats = {}
    for name in ("pending", "archived", "error"):
        folder = os.path.join(directory, name)
        try:
            stats[name] = len(os.listdir(folder))
        except OSError:
            stats[name] = 0
    return stats


def inspect_memory(paths: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """只读检测记忆系统；返回各文件状态与问题清单。"""
    p = _paths(paths)
    config = _inspect_memory_config(p["memory_json"])
    experiences = _inspect_experiences(p["experiences_db"])
    events = _inspect_events(p["events_db"], p["events_table"])
    chroma = _inspect_chroma(p["chroma_dir"])

    issues: List[Dict[str, Any]] = []

    def add(code: str, message: str, file: str, level: str = "warn") -> None:
        issues.append({"code": code, "level": level, "file": file, "message": message})

    cfg_status = config["status"]
    if cfg_status in ("missing", "corrupt", "invalid", "legacy", "outdated"):
        add(f"memory_config_{cfg_status}", _config_message(config), config["path"])
    elif cfg_status == "newer":
        add(
            "memory_config_newer",
            f"memory.json 版本 {config['version']} 高于当前程序（{config['latest']}），已保留不改写",
            config["path"],
        )

    if experiences["exists"]:
        if experiences.get("error"):
            add(
                "experiences_db_unreadable",
                f"experiences.db 无法读取：{experiences['error']}",
                experiences["path"],
                "error",
            )
        else:
            if experiences["missing_tables"]:
                add(
                    "experiences_schema_incomplete",
                    "experiences.db 缺少表："
                    + ", ".join(experiences["missing_tables"]),
                    experiences["path"],
                )
            if (experiences["schema_version"] or 0) < MEMORY_SCHEMA_VERSION:
                add(
                    "experiences_schema_outdated",
                    f"experiences.db 结构版本 {experiences['schema_version']}，需升级到 {MEMORY_SCHEMA_VERSION}",
                    experiences["path"],
                )
            if not experiences["fts_in_sync"]:
                add(
                    "experiences_fts_out_of_sync",
                    f"经验全文索引与主表行数不一致（{experiences['fts_rows']}/{experiences['rows']}），需重建",
                    experiences["path"],
                )

    if events["exists"]:
        if events.get("error"):
            add(
                "events_db_unreadable",
                f"events.db 无法读取：{events['error']}",
                events["path"],
                "error",
            )
        else:
            if events["missing_tables"]:
                add(
                    "events_schema_incomplete",
                    "events.db 缺少表：" + ", ".join(events["missing_tables"]),
                    events["path"],
                )
            if (events["schema_version"] or 0) < MEMORY_SCHEMA_VERSION:
                add(
                    "events_schema_outdated",
                    f"events.db 结构版本 {events['schema_version']}，需升级到 {MEMORY_SCHEMA_VERSION}",
                    events["path"],
                )
            if not events["fts_in_sync"]:
                add(
                    "events_fts_out_of_sync",
                    f"事件全文索引与主表行数不一致（{events['fts_rows']}/{events['rows']}），需重建",
                    events["path"],
                )

    if chroma["exists"] and chroma["readable"] and chroma["missing"]:
        add(
            "chroma_collections_missing",
            "向量库缺少 collection：" + ", ".join(chroma["missing"]),
            chroma["path"],
        )

    return {
        "version": config["version"],
        "latest_version": config["latest"],
        "schema_version": experiences["schema_version"],
        "latest_schema_version": MEMORY_SCHEMA_VERSION,
        "config": config,
        "experiences_db": experiences,
        "events_db": events,
        "chroma": chroma,
        "graph": {"path": p["graph"], "exists": os.path.exists(p["graph"])},
        "buffer": _buffer_stats(p["buffer"]),
        "issues": issues,
        "ok": not issues,
    }


def _config_message(entry: Dict[str, Any]) -> str:
    status = entry["status"]
    if status == "missing":
        return "memory.json 缺失，将自动生成默认配置"
    if status == "corrupt":
        return "memory.json 已损坏，将备份后重建"
    if status == "invalid":
        return "memory.json 顶层不是 JSON 对象，将备份后重建"
    if status == "legacy":
        return "memory.json 为旧版本（无版本号），将自动迁移"
    return f"memory.json 需要更新（版本 {entry['version']} → {entry['latest']}）"


# ==========================================
# 自动迁移
# ==========================================


def _rebuild_fts(
    conn: sqlite3.Connection, table: str, fts_table: str, id_col: str, fts_col: str
) -> int:
    """主表与 FTS 行数不一致时按主表重建，返回重建条数。"""
    from src.memory.purrmemo.core.filters import tokenize_for_fts

    rows = conn.execute(f"SELECT {id_col}, content FROM {table}").fetchall()
    current = _count(conn, fts_table)
    if len(rows) == current:
        return 0
    with conn:
        conn.execute(f"DELETE FROM {fts_table}")
        for row in rows:
            conn.execute(
                f"INSERT INTO {fts_table} ({id_col}, {fts_col}) VALUES (?, ?)",
                (row[0], tokenize_for_fts(row[1] or "")),
            )
    return len(rows)


def _ensure_experiences_db(path: str) -> Dict[str, Any]:
    from src.memory.purrmemo.core.storage.experience_engine import (
        _EVENTS_DDL,
        _FTS_DDL,
        _META_DDL,
        _TABLE_DDL,
    )
    from src.memory.purrmemo.core.storage.outbox import ensure_outbox

    conn = sqlite3.connect(path, check_same_thread=False)
    try:
        with conn:
            conn.execute(_TABLE_DDL)
            conn.execute(_FTS_DDL)
            conn.execute(_EVENTS_DDL)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_experience_events_exp"
                " ON experience_events (exp_id)"
            )
            conn.execute(_META_DDL)
            ensure_outbox(conn)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(experiences)")}
            if "kind" in columns:
                conn.execute("ALTER TABLE experiences DROP COLUMN kind")
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', '2')"
            )
        rebuilt = _rebuild_fts(
            conn, "experiences", "experiences_fts", "exp_id", "tokens"
        )
        return {"schema_version": MEMORY_SCHEMA_VERSION, "rebuilt_fts": rebuilt}
    finally:
        conn.close()


def _ensure_events_db(path: str, table: str) -> Dict[str, Any]:
    from src.memory.purrmemo.core.storage.outbox import ensure_outbox

    conn = sqlite3.connect(path, check_same_thread=False)
    try:
        with conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    event_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    source TEXT
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_timestamp ON {table} (timestamp)"
            )
            conn.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {table}_fts USING fts5(
                    event_id UNINDEXED,
                    content
                )
                """
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_meta ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            ensure_outbox(conn)
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', '2')"
            )
        rebuilt = _rebuild_fts(conn, table, f"{table}_fts", "event_id", "content")
        return {"schema_version": MEMORY_SCHEMA_VERSION, "rebuilt_fts": rebuilt}
    finally:
        conn.close()


def _ensure_chroma_collections(directory: str) -> Dict[str, Any]:
    from src.memory.purrmemo.core.storage.vector_engine import VectorEngine

    engine = VectorEngine(persist_directory=directory)
    names = [
        engine.collection.name,
        engine.events_collection.name,
        engine.graph_collection.name,
    ]
    return {"collections": names}


def migrate_memory(
    paths: Dict[str, Any] | None = None, dry_run: bool = False
) -> Dict[str, Any]:
    """把记忆系统结构与配置迁移到当前版本；单步失败不影响其它步骤。"""
    p = _paths(paths)
    result: Dict[str, Any] = {
        "dry_run": dry_run,
        "config": None,
        "experiences_db": None,
        "events_db": None,
        "vector": None,
        "errors": [],
    }
    if dry_run:
        return result

    # 1. 配置文件（memory.json 等托管配置）
    try:
        from src.utils.config_migration import ConfigSpec, migrate_configs

        if paths is None:
            result["config"] = migrate_configs()
        else:
            from src.memory.settings import DEFAULTS, DEFAULT_KEYS, DEPRECATED_KEYS

            spec = ConfigSpec(
                "memory",
                p["memory_json"],
                lambda: dict(DEFAULTS),
                deprecated=DEPRECATED_KEYS,
                required=DEFAULT_KEYS,
            )
            result["config"] = migrate_configs(
                [spec],
                backup_dir=os.path.join(os.path.dirname(p["memory_json"]), "backups"),
            )
    except Exception as e:
        result["errors"].append(f"配置迁移失败: {e}")

    # 2. SQLite 结构（仅处理已存在的库，不主动为新用户建库）
    if os.path.exists(p["experiences_db"]):
        try:
            result["experiences_db"] = _ensure_experiences_db(p["experiences_db"])
        except Exception as e:
            result["errors"].append(f"经验库迁移失败: {e}")

    if os.path.exists(p["events_db"]):
        try:
            result["events_db"] = _ensure_events_db(p["events_db"], p["events_table"])
        except Exception as e:
            result["errors"].append(f"事件库迁移失败: {e}")

    # 3. 向量库 collection（仅当向量库文件已存在）
    if os.path.exists(os.path.join(p["chroma_dir"], "chroma.sqlite3")):
        try:
            result["vector"] = _ensure_chroma_collections(p["chroma_dir"])
        except Exception as e:
            result["errors"].append(f"向量库迁移失败: {e}")

    return result


# ==========================================
# 启动检查
# ==========================================


def run_startup_check() -> Dict[str, Any]:
    """启动检查：检测 → 有问题自动迁移 → 复检；仍未解决的问题打印日志。"""
    before = inspect_memory()
    migration = None
    if not before["ok"]:
        migration = migrate_memory()
    after = inspect_memory()
    if not after["ok"]:
        print(
            "[!] 记忆系统仍有未修复问题："
            + "；".join(item["message"] for item in after["issues"])
        )
    return {"before": before, "migration": migration, "health": after}

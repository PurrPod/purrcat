import os
import sqlite3

from src.memory.config import EVENTDB_PATH, EVENTDB_TABLE_NAME

from ..clock import iso_days_ago, now_iso
from ..filters import build_fts_query, build_fts_query_or, tokenize_for_fts
from ..utils import SingletonMeta
from .outbox import enqueue, ensure_outbox


class EventEngine(metaclass=SingletonMeta):
    def __init__(self, db_path=None, table_name=None):
        self.db_path = db_path if db_path is not None else EVENTDB_PATH
        self.table_name = table_name if table_name is not None else EVENTDB_TABLE_NAME
        self.conn = None
        self._init_db()

    def _init_db(self):
        """初始化数据库和表结构"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = (
            sqlite3.Row
        )  # 【新增】让 fetchall 直接返回类似 dict 的对象
        self.conn.execute("PRAGMA journal_mode=WAL;")

        cursor = self.conn.cursor()
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            event_id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            source TEXT
        )
        """)

        cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_timestamp 
        ON {self.table_name} (timestamp)
        """)

        cursor.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {self.table_name}_fts USING fts5(
            event_id UNINDEXED, 
            content
        )
        """)

        # 结构版本：供启动健康检测判断事件库是否已升级到当前结构
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        cursor.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', '2')"
        )

        ensure_outbox(self.conn)
        self.conn.commit()

    def insert_event(self, event_id, content, timestamp=None, source=None):
        """插入事件"""
        if timestamp is None:
            timestamp = now_iso()

        try:
            with self.conn:
                self.conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {self.table_name}
                    (event_id, content, timestamp, source)
                    VALUES (?, ?, ?, ?)
                    """,
                    (event_id, content, timestamp, source),
                )
                self.conn.execute(
                    f"DELETE FROM {self.table_name}_fts WHERE event_id = ?", (event_id,)
                )
                self.conn.execute(
                    f"""
                    INSERT INTO {self.table_name}_fts (event_id, content)
                    VALUES (?, ?)
                    """,
                    (event_id, tokenize_for_fts(content)),
                )
                enqueue(self.conn, event_id, "upsert")
            return True
        except Exception as e:
            print(f"插入事件失败: {e}")
            return False

    def get_event_by_id(self, event_id):
        """根据 ID 获取事件"""
        cursor = self.conn.cursor()
        cursor.execute(
            f"""
        SELECT event_id, content, timestamp, source 
        FROM {self.table_name} 
        WHERE event_id = ?
        """,
            (event_id,),
        )

        row = cursor.fetchone()
        return dict(row) if row else None

    def get_events(self, start_time=None, end_time=None, limit=100):
        """【合并优化】一个方法搞定最新查询和区间查询"""
        cursor = self.conn.cursor()
        sql = f"SELECT event_id, content, timestamp, source FROM {self.table_name}"
        params = []

        if start_time and end_time:
            sql += " WHERE timestamp >= ? AND timestamp <= ?"
            params.extend([start_time, end_time])

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, tuple(params))
        # 因为启用了 sqlite3.Row，直接推导式返回即可
        return [dict(row) for row in cursor.fetchall()]

    def _run_fts_query(self, fts_query_str, start_time, end_time, limit):
        sql = f"""
        SELECT e.event_id, e.content, e.timestamp, e.source, fts.rank as bm25_score
        FROM {self.table_name}_fts fts
        JOIN {self.table_name} e ON fts.event_id = e.event_id
        WHERE {self.table_name}_fts MATCH ?
        """
        params = [fts_query_str]

        if start_time and end_time:
            sql += " AND e.timestamp >= ? AND e.timestamp <= ?"
            params.extend([start_time, end_time])

        sql += " ORDER BY fts.rank LIMIT ?"
        params.append(limit)

        cursor = self.conn.execute(sql, tuple(params))
        return [
            {
                "id": r[0],
                "data": {
                    "event_id": r[0],
                    "content": r[1],
                    "timestamp": r[2],
                    "source": r[3],
                },
                "score": abs(r[4]),
            }
            for r in cursor.fetchall()
        ]

    def search_fts_bm25(self, query, start_time=None, end_time=None, limit=50):
        """利用 SQLite FTS5 执行 BM25 检索；AND 零结果时用 OR 重试。"""
        fts_query_str = build_fts_query(query)
        if not fts_query_str:
            return []

        results = self._run_fts_query(fts_query_str, start_time, end_time, limit)
        if results:
            return results

        or_query_str = build_fts_query_or(query)
        if or_query_str and or_query_str != fts_query_str:
            return self._run_fts_query(or_query_str, start_time, end_time, limit)
        return []

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()

    def delete_event(self, event_id):
        """彻底删除单条事件（包含全文索引），并登记向量删除。"""
        try:
            with self.conn:
                cursor = self.conn.execute(
                    f"DELETE FROM {self.table_name} WHERE event_id = ?", (event_id,)
                )
                self.conn.execute(
                    f"DELETE FROM {self.table_name}_fts WHERE event_id = ?", (event_id,)
                )
                if cursor.rowcount > 0:
                    enqueue(self.conn, event_id, "delete")
                    return True
            return False
        except Exception as e:
            print(f"删除事件失败: {e}")
            return False

    def count(self):
        """当前事件总数（配置中心展示用）。"""
        return self.conn.execute(f"SELECT COUNT(*) FROM {self.table_name}").fetchone()[0]

    def list_existing_ids(self):
        """列出 SQLite 中现有的事件 ID，供索引对账使用。"""
        cursor = self.conn.execute(f"SELECT event_id FROM {self.table_name}")
        return [row[0] for row in cursor.fetchall()]

    def list_outbox(self, limit=100, now=None):
        """读取待同步操作（索引器使用）。"""
        from .outbox import fetch_pending

        return fetch_pending(self.conn, limit=limit, now=now)

    def cleanup_old_events(self, days_threshold=90):
        """清理超过 N 天的陈旧事件"""
        cutoff_date = iso_days_ago(days_threshold)

        try:
            with self.conn:
                cursor = self.conn.execute(
                    f"SELECT event_id FROM {self.table_name} WHERE timestamp < ?",
                    (cutoff_date,),
                )
                old_ids = [row[0] for row in cursor.fetchall()]

                if not old_ids:
                    return 0

                self.conn.execute(
                    f"DELETE FROM {self.table_name}_fts WHERE event_id IN "
                    f"(SELECT event_id FROM {self.table_name} WHERE timestamp < ?)",
                    (cutoff_date,),
                )
                self.conn.execute(
                    f"DELETE FROM {self.table_name} WHERE timestamp < ?", (cutoff_date,)
                )
                for event_id in old_ids:
                    enqueue(self.conn, event_id, "delete")
            return len(old_ids)
        except Exception as e:
            print(f"清理陈旧事件失败: {e}")
            return 0

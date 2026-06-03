import os
import sqlite3
from datetime import datetime

from src.utils.config import get_memory_config

from ..utils import SingletonMeta


class EventEngine(metaclass=SingletonMeta):
    def __init__(self):
        config = get_memory_config().get("eventdb", {})
        self.db_path = config.get("db_path", "data/memory/events.db")
        self.table_name = config.get("table_name", "events")
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
        self.conn.commit()

    def insert_event(self, event_id, content, timestamp=None, source=None):
        """插入事件"""
        if timestamp is None:
            timestamp = datetime.now().isoformat()

        try:
            cursor = self.conn.cursor()
            cursor.execute(
                f"""
            INSERT OR REPLACE INTO {self.table_name} 
            (event_id, content, timestamp, source) 
            VALUES (?, ?, ?, ?)
            """,
                (event_id, content, timestamp, source),
            )

            cursor.execute(
                f"DELETE FROM {self.table_name}_fts WHERE event_id = ?", (event_id,)
            )
            cursor.execute(
                f"""
            INSERT INTO {self.table_name}_fts (event_id, content) 
            VALUES (?, ?)
            """,
                (event_id, content),
            )

            self.conn.commit()
            return True
        except Exception as e:
            print(f"插入事件失败: {e}")
            self.conn.rollback()
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

    def search_fts_bm25(self, query, start_time=None, end_time=None, limit=50):
        """利用 SQLite FTS5 执行 BM25 检索"""
        cursor = self.conn.cursor()

        clean_query = query.replace('"', "").replace("'", "").strip()
        tokens = clean_query.split()
        if not tokens:
            return []

        fts_query_str = " AND ".join([f'"{t}"*' for t in tokens])

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

        cursor.execute(sql, tuple(params))
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

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()

    def delete_event(self, event_id):
        """彻底删除单条事件（包含全文索引）"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                f"DELETE FROM {self.table_name}_fts WHERE event_id = ?", (event_id,)
            )
            cursor.execute(
                f"DELETE FROM {self.table_name} WHERE event_id = ?", (event_id,)
            )

            if cursor.rowcount > 0:
                self.conn.commit()
                return True
            else:
                self.conn.rollback()
                return False
        except Exception as e:
            print(f"删除事件失败: {e}")
            self.conn.rollback()
            return False

    def cleanup_old_events(self, days_threshold=90):
        """清理超过 N 天的陈旧事件"""
        from datetime import timedelta

        cutoff_date = (datetime.now() - timedelta(days=days_threshold)).isoformat()

        try:
            cursor = self.conn.cursor()
            cursor.execute(
                f"SELECT event_id FROM {self.table_name} WHERE timestamp < ?",
                (cutoff_date,),
            )
            old_ids = [row[0] for row in cursor.fetchall()]

            if not old_ids:
                return 0

            cursor.execute(
                f"DELETE FROM {self.table_name}_fts WHERE event_id IN (SELECT event_id FROM {self.table_name} WHERE timestamp < ?)",
                (cutoff_date,),
            )
            cursor.execute(
                f"DELETE FROM {self.table_name} WHERE timestamp < ?", (cutoff_date,)
            )
            self.conn.commit()
            return len(old_ids)
        except Exception as e:
            print(f"清理陈旧事件失败: {e}")
            self.conn.rollback()
            return 0

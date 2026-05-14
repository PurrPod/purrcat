import sqlite3
import json
import os
import threading
from datetime import datetime
from ..config import EVENT_DATABASE_CONFIG

class EventEngine:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EventEngine, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self.db_path = EVENT_DATABASE_CONFIG['db_path']
        self.table_name = EVENT_DATABASE_CONFIG['table_name']
        self.conn = None
        self._init_db()
        self._initialized = True
    
    def _init_db(self):
        """初始化数据库和表结构"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # 开启 WAL 模式以支持读写并发
        self.conn.execute("PRAGMA journal_mode=WAL;")
        
        # 创建事件表
        cursor = self.conn.cursor()
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            event_id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            vector TEXT,  -- 存储向量的 JSON 字符串
            timestamp TEXT NOT NULL,
            source TEXT
        )
        """)
        
        # 创建时间索引
        cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_timestamp 
        ON {self.table_name} (timestamp)
        """)
        
        # 创建 FTS5 虚拟表，用于全文字面量/BM25检索
        cursor.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {self.table_name}_fts USING fts5(
            event_id UNINDEXED, 
            content
        )
        """)
        self.conn.commit()
    
    def insert_event(self, event_id, content, vector=None, timestamp=None, source=None):
        """插入事件
        
        Args:
            event_id: 事件唯一标识
            content: 事件内容
            vector: 事件向量（可选）
            timestamp: 时间戳（可选，默认当前时间）
            source: 事件来源（可选）
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        vector_str = json.dumps(vector) if vector else None
        
        try:
            cursor = self.conn.cursor()
            # 1. 插入主表 (这个 OR REPLACE 是生效的，因为有 PRIMARY KEY)
            cursor.execute(f"""
            INSERT OR REPLACE INTO {self.table_name} 
            (event_id, content, vector, timestamp, source) 
            VALUES (?, ?, ?, ?, ?)
            """, (event_id, content, vector_str, timestamp, source))
            
            # 2. 插入 FTS5 表 (必须先删后插，防止重复)
            cursor.execute(f"DELETE FROM {self.table_name}_fts WHERE event_id = ?", (event_id,))
            cursor.execute(f"""
            INSERT INTO {self.table_name}_fts (event_id, content) 
            VALUES (?, ?)
            """, (event_id, content))
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"插入事件失败: {e}")
            self.conn.rollback()
            return False
    
    def get_event_by_id(self, event_id):
        """根据 ID 获取事件"""
        cursor = self.conn.cursor()
        cursor.execute(f"""
        SELECT event_id, content, vector, timestamp, source 
        FROM {self.table_name} 
        WHERE event_id = ?
        """, (event_id,))
        
        row = cursor.fetchone()
        if row:
            vector = json.loads(row[2]) if row[2] else None
            return {
                'event_id': row[0],
                'content': row[1],
                'vector': vector,
                'timestamp': row[3],
                'source': row[4]
            }
        return None
    
    def get_events_by_time_range(self, start_time, end_time, limit=100):
        """根据时间范围获取事件"""
        cursor = self.conn.cursor()
        cursor.execute(f"""
        SELECT event_id, content, vector, timestamp, source
        FROM {self.table_name}
        WHERE timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp DESC
        LIMIT ?
        """, (start_time, end_time, limit))

        events = []
        for row in cursor.fetchall():
            vector = json.loads(row[2]) if row[2] else None
            events.append({
                'event_id': row[0],
                'content': row[1],
                'vector': vector,
                'timestamp': row[3],
                'source': row[4]
            })
        return events

    def get_latest_events(self, limit=100):
        """获取最新的事件"""
        cursor = self.conn.cursor()
        cursor.execute(f"""
        SELECT event_id, content, vector, timestamp, source
        FROM {self.table_name}
        ORDER BY timestamp DESC
        LIMIT ?
        """, (limit,))

        events = []
        for row in cursor.fetchall():
            vector = json.loads(row[2]) if row[2] else None
            events.append({
                'event_id': row[0],
                'content': row[1],
                'vector': vector,
                'timestamp': row[3],
                'source': row[4]
            })
        return events

    def search_fts_bm25(self, query, start_time=None, end_time=None, limit=50):
        """利用 SQLite FTS5 执行 BM25 检索，并支持时间过滤"""
        cursor = self.conn.cursor()

        clean_query = query.replace('"', '').replace("'", "").strip()

        tokens = clean_query.split()
        if not tokens:
            return []
        fts_query_str = " AND ".join([f'"{t}"*' for t in tokens])

        sql = f"""
        SELECT e.event_id, e.content, e.vector, e.timestamp, e.source, fts.rank as bm25_score
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

        results = [{"id": r[0], "data": {'event_id': r[0], 'content': r[1], 'vector': json.loads(r[2]) if r[2] else None, 'timestamp': r[3], 'source': r[4]}, "score": abs(r[5])} for r in cursor.fetchall()]
        return results

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()



"""记忆系统内部配置（不对外暴露，用户无需修改）"""

# ── ChromaDB 向量数据库 ──
CHROMADB_PERSIST_DIRECTORY = "data/memory/chromadb"
CHROMADB_COLLECTION_NAME = "experiences"
CHROMADB_GRAPH_COLLECTION_NAME = "graph_nodes"
CHROMADB_EVENTS_COLLECTION_NAME = "events"

# ── 事件数据库 (SQLite) ──
EVENTDB_PATH = "data/memory/events.db"
EVENTDB_TABLE_NAME = "events"

# ── 图谱数据库 ──
GRAPHDB_PATH = "data/memory/graph.pkl"
GRAPHDB_MIN_CONFIDENCE = 0.3

# ── 记忆工人 ──
MEMORY_AGENT_POLLING_INTERVAL = 5

# ── RAG 检索参数 ──
RAG_TOP_K_EVENTS = 5
RAG_TOP_K_EXPERIENCES = 5
RAG_TOP_K_GRAPH_NODES = 3
RAG_MAX_GRAPH_DEPTH = 2

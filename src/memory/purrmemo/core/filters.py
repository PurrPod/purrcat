"""检索结果的纯过滤与查询构造（SPEC-012 / SPEC-020）。"""

from __future__ import annotations

from datetime import datetime

from .schema import MIN_VECTOR_SCORE

_jieba_module = None


def _jieba():
    """懒加载 jieba，避免记忆栈导入时加载词典。"""
    global _jieba_module
    if _jieba_module is None:
        import jieba

        _jieba_module = jieba
    return _jieba_module


def clamp_top_k(top_k: int, available: int) -> int:
    """请求条数不超过底层集合实际数量。"""
    return min(top_k, available)


def filter_by_time_range(items, start_time, end_time):
    """保留 ``data.timestamp`` 落在闭区间内的事件结果。"""
    return [
        item for item in items if start_time <= item["data"]["timestamp"] <= end_time
    ]


def filter_experiences_by_score(items, min_score=MIN_VECTOR_SCORE):
    """按相似度阈值过滤经验结果。"""
    return [item for item in items if item["score"] >= min_score]


def tokenize_for_fts(text: str) -> str:
    """用 jieba 搜索引擎模式分词，返回空格连接的 FTS token 串（SPEC-020 4.4）。"""
    if not text:
        return ""
    clean_query = text.replace('"', "").replace("'", "").replace("*", "").strip()
    if not clean_query:
        return ""
    tokens = []
    for raw in _jieba().cut_for_search(clean_query):
        token = raw.strip().lower()
        if not token or not any(ch.isalnum() for ch in token):
            continue
        tokens.append(token)
    return " ".join(tokens)


def build_fts_query(query: str) -> str | None:
    """把用户查询转为 FTS5 的 AND 前缀查询；无有效词时返回 ``None``。"""
    tokens = tokenize_for_fts(query).split()
    if not tokens:
        return None
    return " AND ".join([f'"{t}"*' for t in tokens])


def build_fts_query_or(query: str) -> str | None:
    """零结果时使用的 OR 降级查询；无有效词时返回 ``None``。"""
    tokens = tokenize_for_fts(query).split()
    if not tokens:
        return None
    return " OR ".join([f'"{t}"*' for t in tokens])


def date_range_for(raw_date: str) -> tuple[str, str]:
    """把 ``YYYY-MM-DD`` 转为当天的 ISO 起止时间；非法格式抛 ``ValueError``。"""
    parsed = datetime.strptime(raw_date.strip(), "%Y-%m-%d")
    start_time = parsed.strftime("%Y-%m-%dT00:00:00")
    end_time = parsed.strftime("%Y-%m-%dT23:59:59.999999")
    return start_time, end_time

"""检索结果的纯过滤与查询构造（SPEC-012）。"""

from __future__ import annotations

from datetime import datetime

from .schema import MIN_EXPERIENCE_SCORE


def clamp_top_k(top_k: int, available: int) -> int:
    """请求条数不超过底层集合实际数量。"""
    return min(top_k, available)


def filter_by_time_range(items, start_time, end_time):
    """保留 ``data.timestamp`` 落在闭区间内的事件结果。"""
    return [
        item for item in items if start_time <= item["data"]["timestamp"] <= end_time
    ]


def filter_experiences_by_score(items, min_score=MIN_EXPERIENCE_SCORE):
    """按相似度阈值过滤经验结果。"""
    return [item for item in items if item["score"] >= min_score]


def build_fts_query(query: str) -> str | None:
    """把用户查询转为 FTS5 的 AND 前缀查询；无有效词时返回 ``None``。"""
    clean_query = query.replace('"', "").replace("'", "").strip()
    tokens = clean_query.split()
    if not tokens:
        return None
    return " AND ".join([f'"{t}"*' for t in tokens])


def date_range_for(raw_date: str) -> tuple[str, str]:
    """把 ``YYYY-MM-DD`` 转为当天的 ISO 起止时间；非法格式抛 ``ValueError``。"""
    parsed = datetime.strptime(raw_date.strip(), "%Y-%m-%d")
    start_time = parsed.strftime("%Y-%m-%dT00:00:00")
    end_time = parsed.strftime("%Y-%m-%dT23:59:59.999999")
    return start_time, end_time

"""检索与经验库共享的常量（SPEC-012）。"""

# 默认检索条数
DEFAULT_SEARCH_TOP_K = 5
# 混合检索第一阶段的候选池大小
CANDIDATE_LIMIT = 200
# 经验命中阈值（含边界）
MIN_EXPERIENCE_SCORE = 0.30
# 事件混合检索的 RRF 常数，用于把融合分归一化到 0–1
RRF_K = 60
# 图谱节点向量召回条数与候选放大倍数
GRAPH_NODE_SEARCH_TOP_K = 5
GRAPH_NODE_CANDIDATE_FACTOR = 2
# 图谱节点文本命中的加权
GRAPH_NODE_EXACT_BOOST = 2.0
GRAPH_NODE_PARTIAL_BOOST = 0.5

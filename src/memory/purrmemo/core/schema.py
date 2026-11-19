"""检索与经验库共享的常量（SPEC-012 / SPEC-020）。"""

# 默认检索条数
DEFAULT_SEARCH_TOP_K = 5
# 混合检索第一阶段的候选池大小
CANDIDATE_LIMIT = 200
# 向量检索命中阈值（经验、图谱节点共用，含边界）
MIN_VECTOR_SCORE = 0.30
# 事件检索默认阈值：e5-small 余弦分布集中高位，0.80 在三套中英文语料上
# 不损失 R@10，同时显著减少无关候选
MIN_EVENT_VECTOR_SCORE = 0.80
# 事件混合检索的 RRF 常数，仅用于合并候选与截断
RRF_K = 60
# 事件检索的加权 RRF：向量权重 0.6 / BM25 0.4，k=10（SPEC-042 实测最优）
EVENT_RRF_K = 10
EVENT_RRF_VECTOR_WEIGHT = 0.6
# 图谱节点向量召回条数与候选放大倍数
GRAPH_NODE_SEARCH_TOP_K = 5
GRAPH_NODE_CANDIDATE_FACTOR = 2
# 图谱节点文本命中的加权
GRAPH_NODE_EXACT_BOOST = 2.0
GRAPH_NODE_PARTIAL_BOOST = 0.5

# ── 经验置信度（SPEC-020）──
# 新经验初始置信度
NEW_EXPERIENCE_CONFIDENCE = 0.6
# 每次 reinforce 的增量
REINFORCE_INCREMENT = 0.2
# 置信度下限（不自动删除）
CONFIDENCE_FLOOR = 0.3
# 艾宾浩斯半衰期天数
DECAY_HALF_LIFE_DAYS = 90.0

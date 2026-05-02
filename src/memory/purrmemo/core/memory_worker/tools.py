from pydantic import BaseModel, Field
import datetime
import hashlib
from src.memory.purrmemo.core.storage.graph_engine import GraphEngine

graph_engine = None

def init_graph_engine():
    global graph_engine
    if graph_engine is None:
        graph_engine = GraphEngine()

def get_node_id(node_name: str) -> str:
    """生成稳定的节点 ID
    
    Args:
        node_name: 节点名称
    
    Returns:
        稳定的节点 ID
    """
    # 清洗节点名称：去空格、统一小写
    cleaned_node_name = node_name.strip().lower()
    return f"node_{hashlib.md5(cleaned_node_name.encode()).hexdigest()[:8]}"

def add_relation(source_node: str, relation: str, target_node: str, source_event_id: str = "unknown") -> str:
    """
    【新增联系】当检索发现知识库中不存在该事实，或者需要建立层级关系(如红富士-属于-苹果)时使用。

    Args:
        source_node: 起始节点名称，如 "用户"
        relation: 联系的含义，如 "喜欢吃", "属于"
        target_node: 目标节点名称，如 "苹果"
        source_event_id: 来源事件ID，用于溯源
    """
    init_graph_engine()
    source_node_id = get_node_id(source_node)
    target_node_id = get_node_id(target_node)

    graph_engine.add_node(source_node_id, source_node)
    graph_engine.add_node(target_node_id, target_node)
    success = graph_engine.add_relation(source_node_id, target_node_id, relation, confidence=0.5, source_event_id=source_event_id)

    if success:
        return f"成功添加新关系：({source_node}) -[{relation}]-> ({target_node})"
    return f"添加关系失败：({source_node}) -[{relation}]-> ({target_node})"


def reinforce_relation(source_node: str, relation: str, target_node: str) -> str:
    """
    【强化联系】当新的认知与知识库中已有的关系一致时使用，用于提升该关系的置信度（Confidence）。

    Args:
        source_node: 起始节点名称
        relation: 联系的含义
        target_node: 目标节点名称
    """
    init_graph_engine()
    source_node_id = get_node_id(source_node)
    target_node_id = get_node_id(target_node)

    success = graph_engine.reinforce_relation(source_node_id, target_node_id, relation, increment=0.1)

    if success:
        return f"成功强化已有关系，置信度已提升。"
    return f"强化关系失败：未找到 ({source_node}) -[{relation}]-> ({target_node})"


def weaken_relation(source_node: str, relation: str, target_node: str, reason: str) -> str:
    """
    【削弱联系】当新的认知与知识库中已有的关系产生冲突时使用，用于降低旧关系的置信度。
    注意：削弱旧关系后，通常需要紧接着调用 add_relation 添加新的正确关系。

    Args:
        source_node: 起始节点名称
        relation: 联系的含义
        target_node: 目标节点名称
        reason: 为什么要削弱它的理由
    """
    init_graph_engine()
    source_node_id = get_node_id(source_node)
    target_node_id = get_node_id(target_node)

    success = graph_engine.weaken_relation(source_node_id, target_node_id, relation, decrement=0.2)

    if success:
        return f"成功削弱已有关系，置信度已降低。原因：{reason}"
    return f"削弱关系失败：未找到 ({source_node}) -[{relation}]-> ({target_node})"


def rag_search(entity_keyword: str) -> str:
    """
    【图谱检索工具】在执行添加(add)、削弱(weaken)或强化(reinforce)操作前，必须且优先调用此工具！
    用于检索知识库中是否已经存在相关的实体（Node）或它们之间的联系（Edge）。

    Args:
        entity_keyword: 认知信息中的核心实体或关键词。例如，如果新信息是"用户喜欢吃红富士"，此处应传入 "红富士" 或 "苹果"。

    Returns:
        包含与该实体相关的现有关系列表文本。如果返回空，说明是全新的知识。
    """
    init_graph_engine()
    results = []

    try:
        if graph_engine.vector_engine:
            similar_nodes = graph_engine.vector_engine.search_graph_nodes(entity_keyword, top_k=3)
        else:
            # 无向量引擎时，直接返回空结果
            similar_nodes = []
    except Exception as e:
        print(f"搜索图谱节点失败: {e}")
        similar_nodes = []
    
    for node_info in similar_nodes:
        node_id = node_info['node_id']
        relations = graph_engine.get_relations_by_node(node_id, direction='all')
        for rel in relations:
            target = graph_engine.get_node(rel['target_node_id'])
            target_name = target['name'] if target else '未知'
            source = graph_engine.get_node(rel['source_node_id'])
            source_name = source['name'] if source else '未知'
            results.append(
                f"- 节点ID: {rel['source_node_id']} (实体: {source_name})\n"
                f"  节点ID: {rel['target_node_id']} (实体: {target_name})\n"
                f"  现有关系: ({source_name}) -[{rel['relation_meaning']}]-> ({target_name}) | 置信度: {rel['confidence']} | 来源: {rel.get('source_event_id', 'unknown')}"
            )

    if results:
        return "【检索到的现有知识库状态】\n" + "\n".join(results)
    else:
        return f"【检索结果】未找到与 '{entity_keyword}' 相关的现有节点或联系，这是一个全新的知识。"


MEMORY_WORKER_TOOLS = [
    rag_search,
    add_relation,
    reinforce_relation,
    weaken_relation
]

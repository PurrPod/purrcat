"""记忆工人 LLM 工具定义（SPEC-012）。"""

WRITE_TOOL_NAMES = ("add_relation", "reinforce_relation", "weaken_relation")

MEMORY_WORKER_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": "批量检索知识库中是否存在相关节点",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "关键词列表，从认知信息中提取的核心实体",
                    }
                },
                "required": ["entity_keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_relation",
            "description": "新增三元组关系",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_node": {"type": "string"},
                    "relation": {"type": "string"},
                    "target_node": {"type": "string"},
                    "source_event_id": {"type": "string", "default": "unknown"},
                },
                "required": ["source_node", "relation", "target_node"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reinforce_relation",
            "description": "强化已有关系",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_node": {"type": "string"},
                    "relation": {"type": "string"},
                    "target_node": {"type": "string"},
                },
                "required": ["source_node", "relation", "target_node"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "weaken_relation",
            "description": "削弱已有关系（通常需要紧接着 add_relation）",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_node": {"type": "string"},
                    "relation": {"type": "string"},
                    "target_node": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "source_node",
                    "relation",
                    "target_node",
                    "reason",
                ],
            },
        },
    },
]

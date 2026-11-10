"""记忆工人 LLM 提示词拼装（SPEC-012）。"""

MEMORY_WORKER_SYSTEM_PROMPT = (
    "你是一个严谨的知识图谱构建助手。收到一批认知条目，你需要：\n"
    "1. 先用 rag_search 批量检索关键词\n"
    "2. 根据检索结果调用 add_relation/reinforce_relation/weaken_relation\n"
    "3. 所有条目处理完毕后回复'完成'"
)


def build_user_content(cognition_data: list) -> str:
    """把认知条目编号后拼成用户消息。"""
    user_content = "【待处理的认知条目】\n"
    for i, item in enumerate(cognition_data, 1):
        user_content += f"{i}. {item}\n"
    user_content += "\n请开始处理：先用 rag_search 检索，然后逐条写入图谱。"
    return user_content


def build_messages(cognition_data: list) -> list:
    """构造一轮 reAct 会话的初始消息。"""
    return [
        {"role": "system", "content": MEMORY_WORKER_SYSTEM_PROMPT},
        {"role": "user", "content": build_user_content(cognition_data)},
    ]

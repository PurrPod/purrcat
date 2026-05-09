"""
LLM 调用辅助函数：将 LLM 调用逻辑提取为纯函数，便于多个节点复用

核心设计原则：
1. 纯函数：不依赖外部状态，输入确定则输出确定
2. 无副作用：不修改传入参数
3. 可测试：易于单元测试
"""
import asyncio
import copy
from typing import Any, List, Dict


async def call_llm(model, messages: List[dict], tools: List[dict] = None, node_log_func=None, context=None) -> tuple:
    """
    调用大模型并返回响应和更新后的消息列表
    
    Args:
        model: 模型实例
        messages: 消息列表（会被深拷贝，不会污染原列表）
        tools: 工具列表
        node_log_func: 日志记录函数
        context: 上下文对象
        
    Returns:
        (response, updated_messages): 响应对象和更新后的消息列表
    """
    # 深拷贝避免污染上游节点数据
    messages_copy = copy.deepcopy(messages)
    
    if node_log_func and context:
        node_log_func(context, "SYSTEM", f"🚀 开始执行大模型请求，当前消息数: {len(messages_copy)}")
    
    try:
        # 使用 asyncio.to_thread 避免阻塞事件循环
        response = await asyncio.to_thread(model.chat, messages=messages_copy, tools=tools or [])
        assistant_msg = response.choices[0].message
        messages_copy.append(assistant_msg.model_dump(exclude_none=True))
        
        if node_log_func and context:
            node_log_func(context, "THOUGHT", f"模型思考结果：{assistant_msg.content}")
        
        return response, messages_copy
    
    except Exception as e:
        if node_log_func and context:
            node_log_func(context, "ERROR", f"❌ 大模型调用崩溃: {e}")
        raise e


def inject_force_push(messages: List[dict], force_push_msgs: List[str]) -> List[dict]:
    """
    将强制注入的消息注入到消息列表中
    
    Args:
        messages: 原始消息列表
        force_push_msgs: 要注入的消息列表
        
    Returns:
        更新后的消息列表
    """
    if not force_push_msgs:
        return messages
    
    # 在列表末尾追加强制注入的消息
    messages_copy = copy.deepcopy(messages)
    for content in force_push_msgs:
        messages_copy.append({
            "role": "user",
            "content": content
        })
    
    return messages_copy

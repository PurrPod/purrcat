"""LLM 调用重试策略的纯函数：模型名清洗、可重试判定、退避时长。"""

import random

from openai import APIConnectionError, InternalServerError

MAX_RETRIES = 8
BASE_DELAY_SECONDS = 2.0


def strip_model_prefix(model_name: str) -> str:
    """`provider:model` 只保留冒号后的模型名。"""
    if ":" in model_name:
        return model_name.split(":")[1]
    return model_name


def is_retryable_error(error: Exception) -> bool:
    """限速、连接断开、服务端崩溃/网关错误可重试；参数/权限错误不可重试。"""
    message = str(error).lower()
    return (
        "rate limit" in message
        or "429" in message
        or "too many requests" in message
        or isinstance(error, (APIConnectionError, InternalServerError))
        or "502" in message
        or "503" in message
        or "504" in message
    )


def backoff_seconds(attempt: int, jitter: float | None = None) -> float:
    """指数退避；jitter 默认取 [0.8, 1.2] 抖动。"""
    if jitter is None:
        jitter = random.uniform(0.8, 1.2)
    return BASE_DELAY_SECONDS * (2**attempt) * jitter

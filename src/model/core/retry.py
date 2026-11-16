"""LLM 调用重试策略的纯函数：模型名清洗、可重试判定、退避时长。"""

import random

MAX_RETRIES = 8
BASE_DELAY_SECONDS = 2.0

# openai 首次导入约 1.5s（全量生成类型树），不能压在启动路径上。
# 这两个名字保持模块级可赋值，测试仍可用 monkeypatch 替换成自己的异常类型。
APIConnectionError: type[BaseException] | None = None
InternalServerError: type[BaseException] | None = None


def _load_openai_errors() -> None:
    """延迟加载 openai 异常类型；已被替换的（测试替身）不覆盖。"""
    global APIConnectionError, InternalServerError

    from openai import APIConnectionError as _api_connection_error
    from openai import InternalServerError as _internal_server_error

    if APIConnectionError is None:
        APIConnectionError = _api_connection_error
    if InternalServerError is None:
        InternalServerError = _internal_server_error


def strip_model_prefix(model_name: str) -> str:
    """`provider:model` 只保留冒号后的模型名。"""
    if ":" in model_name:
        return model_name.split(":")[1]
    return model_name


def is_retryable_error(error: Exception) -> bool:
    """限速、连接断开、服务端崩溃/网关错误可重试；参数/权限错误不可重试。"""
    message = str(error).lower()
    if (
        "rate limit" in message
        or "429" in message
        or "too many requests" in message
        or "502" in message
        or "503" in message
        or "504" in message
    ):
        return True

    # 消息看不出来时才按异常类型判定（等价于原先并列的 isinstance 分支）
    _load_openai_errors()
    return isinstance(error, (APIConnectionError, InternalServerError))


def backoff_seconds(attempt: int, jitter: float | None = None) -> float:
    """指数退避；jitter 默认取 [0.8, 1.2] 抖动。"""
    if jitter is None:
        jitter = random.uniform(0.8, 1.2)
    return BASE_DELAY_SECONDS * (2**attempt) * jitter

import random
import time
import traceback

from openai import (
    APIError,
    APIConnectionError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


class LLMClient:
    """纯粹的执行器，负责 OpenAI Client 的实例化与重试策略"""

    def __init__(self, api_key: str, base_url: str):
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=60.0,  # 强制设定 30 秒超时，避免无限期挂起
        )

    def execute_chat(
        self,
        model_name: str,
        messages: list,
        task_id: str,
        semaphore,
        tools: list = None,
        **kwargs,
    ):
        """执行同步阻塞请求，处理限速和退避"""
        max_retries = 8
        base_delay = 2.0
        if ":" in model_name:
            model_name = model_name.split(":")[1]
        request_params = {"model": model_name, "messages": messages}
        if tools:
            request_params["tools"] = tools
        request_params.update(kwargs)

        for attempt in range(max_retries):
            try:
                with semaphore:
                    time.sleep(0.2)
                    return self.client.chat.completions.create(**request_params)
            except (RateLimitError, APIError) as e:
                error_msg = str(e).lower()
                # 判断是否属于需要重试的异常类型（限速、连接断开、服务端崩溃/网关错误）
                is_retryable = (
                    "rate limit" in error_msg
                    or "429" in error_msg
                    or "too many requests" in error_msg
                    or isinstance(e, (APIConnectionError, InternalServerError))
                    or "502" in error_msg
                    or "503" in error_msg
                    or "504" in error_msg
                )

                if is_retryable:
                    if attempt == max_retries - 1:
                        log(f"❌ 任务 {task_id} 触发限速或网络中断，已达最大重试次数")
                        raise Exception(f"RetryLimitExceeded: {e}")
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = base_delay * (2**attempt) * jitter
                    log(
                        f"⏳ 任务 {task_id} 遇到临时网络异常 ({type(e).__name__})，退避休眠 {sleep_time:.1f} 秒后重试..."
                    )
                    time.sleep(sleep_time)
                else:
                    # 对于明确的参数错误 (400) 或权限错误 (401/403)，不应重试，直接抛出
                    log(f"🚨 API 调用发生不可恢复异常:\n{traceback.format_exc()}")
                    raise e
            except Exception as e:
                log(f"🚨 系统或网络异常:\n{traceback.format_exc()}")
                raise e

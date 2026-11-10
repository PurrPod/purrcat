import time
import traceback

from openai import APIError, OpenAI, RateLimitError

from src.model.core.retry import (
    MAX_RETRIES,
    backoff_seconds,
    is_retryable_error,
    strip_model_prefix,
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
        cancel_event=None,
        **kwargs,
    ):
        """执行同步阻塞请求，处理限速和退避；cancel_event 置位时立即中止重试"""
        model_name = strip_model_prefix(model_name)
        request_params = {"model": model_name, "messages": messages}
        if tools:
            request_params["tools"] = tools
        request_params.update(kwargs)

        for attempt in range(MAX_RETRIES):
            if cancel_event is not None and cancel_event.is_set():
                log(f"🛑 任务 {task_id} 检测到用户打断信号，放弃后续重试")
                raise InterruptedError(f"cancelled: 任务 {task_id} 被用户打断")
            try:
                with semaphore:
                    time.sleep(0.2)
                    return self.client.chat.completions.create(**request_params)
            except (RateLimitError, APIError) as e:
                if is_retryable_error(e):
                    if attempt == MAX_RETRIES - 1:
                        log(f"❌ 任务 {task_id} 触发限速或网络中断，已达最大重试次数")
                        raise Exception(f"RetryLimitExceeded: {e}")
                    sleep_time = backoff_seconds(attempt)
                    log(
                        f"⏳ 任务 {task_id} 遇到临时网络异常 ({type(e).__name__})，退避休眠 {sleep_time:.1f} 秒后重试..."
                    )
                    # 可打断退避：等待期间收到用户打断信号立即放弃重试
                    if cancel_event is not None:
                        if cancel_event.wait(sleep_time):
                            log(f"🛑 任务 {task_id} 在退避等待中被用户打断，放弃重试")
                            raise InterruptedError(
                                f"cancelled: 任务 {task_id} 被用户打断"
                            )
                    else:
                        time.sleep(sleep_time)
                else:
                    # 对于明确的参数错误 (400) 或权限错误 (401/403)，不应重试，直接抛出
                    log(f"🚨 API 调用发生不可恢复异常:\n{traceback.format_exc()}")
                    raise e
            except Exception as e:
                log(f"🚨 系统或网络异常:\n{traceback.format_exc()}")
                raise e

import time
import random
import traceback
from openai import OpenAI, RateLimitError, APIError


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


class LLMClient:
    """纯粹的执行器，负责 OpenAI Client 的实例化与重试策略"""

    def __init__(self, api_key: str, base_url: str):
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=120.0
        )

    def execute_chat(self, model_name: str, messages: list, task_id: str, semaphore, tools: list = None, **kwargs):
        """执行同步阻塞请求，处理限速和退避"""
        max_retries = 8
        base_delay = 2.0
        if ':' in model_name:
            model_name = model_name.split(':')[1]
        request_params = {"model": model_name, "messages": messages}
        if tools:
            request_params["tools"] = tools
        request_params.update(kwargs)

        for attempt in range(max_retries):
            try:
                with semaphore:
                    time.sleep(1.0)
                    return self.client.chat.completions.create(**request_params)
            except (RateLimitError, APIError) as e:
                error_msg = str(e).lower()
                if "rate limit" in error_msg or "429" in error_msg or "too many requests" in error_msg:
                    if attempt == max_retries - 1:
                        log(f"❌ 任务 {task_id} 触发限速，已达最大重试次数")
                        raise Exception(f"RateLimitExceeded: {e}")
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = base_delay * (2 ** attempt) * jitter
                    log(f"⏳ 任务 {task_id} 触发 429 限速，强退避休眠 {sleep_time:.1f} 秒...")
                    time.sleep(sleep_time)
                else:
                    log(f"🚨 API 调用异常:\n{traceback.format_exc()}")
                    raise e
            except Exception as e:
                log(f"🚨 系统或网络异常:\n{traceback.format_exc()}")
                raise e
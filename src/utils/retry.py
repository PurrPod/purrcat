"""
API 调用重试与限速处理模块
支持自动切换 api-key 并重试
"""
import time
from typing import Callable, Any, Optional
from openai import RateLimitError, APIError


def handle_rate_limit(model_instance, max_retries: int = 3, backoff_factor: float = 1.5):
    """
    装饰器：处理 API 限速异常，自动轮询 api-key 并重试
    
    Args:
        model_instance: Model 实例（需要有 rotate_api_key 方法）
        max_retries: 最大重试次数
        backoff_factor: 退避因子（每次重试等待时间 = base_delay * backoff_factor^n）
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs) -> Any:
            base_delay = 1  # 基础延迟 1 秒
            retries = 0
            last_exception = None
            
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except RateLimitError as e:
                    last_exception = e
                    retries += 1
                    masked_key = model_instance.get_current_api_key_masked()
                    print(f"⚠️ [限速异常] api-key ({masked_key}) 被限速，"
                          f"将在 {base_delay} 秒后轮询下一个 api-key... (重试 {retries}/{max_retries})")
                    
                    # 等待后重试
                    time.sleep(base_delay)
                    model_instance.rotate_api_key()
                    base_delay = base_delay * backoff_factor
                    
                except APIError as e:
                    # 其他 API 错误，也尝试轮询
                    last_exception = e
                    retries += 1
                    if "rate limit" in str(e).lower() or "429" in str(e):
                        masked_key = model_instance.get_current_api_key_masked()
                        print(f"⚠️ [API 限速] api-key ({masked_key}) 触发限速，"
                              f"将在 {base_delay} 秒后轮询下一个 api-key... (重试 {retries}/{max_retries})")
                        time.sleep(base_delay)
                        model_instance.rotate_api_key()
                        base_delay = base_delay * backoff_factor
                    else:
                        # 非限速的 API 错误，直接抛出
                        raise
                
                except Exception as e:
                    # 其他异常直接抛出，不重试
                    raise
            
            # 超过最大重试次数，抛出最后一个异常
            if last_exception:
                print(f"❌ [重试失败] 已达到最大重试次数 ({max_retries})，放弃请求")
                raise last_exception
        
        return wrapper
    return decorator


def retry_with_model(model_instance, max_retries: int = 3):
    """
    便捷装饰器：自动为 model.client.chat.completions.create 添加重试逻辑
    
    使用方式：
        @retry_with_model(model_instance)
        def call_llm():
            return model_instance.client.chat.completions.create(...)
    
    Args:
        model_instance: Model 实例
        max_retries: 最大重试次数
    """
    return handle_rate_limit(model_instance, max_retries=max_retries, backoff_factor=1.5)

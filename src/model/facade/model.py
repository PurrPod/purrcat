from src.model.core.llm_client import LLMClient
from src.model.manager.concurrency import get_key_semaphore
from src.model.manager.key_manager import key_manager
from src.model.manager.usage_tracer import usage_tracer
from src.utils.config import get_model_config
import time


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


class Model:
    """提供给业务层的轻量级入口，只维护上下文状态"""

    def __init__(
        self, model_name: str, task_id: str = None, recovered_key_prefix: str = None
    ):
        if not model_name:
            raise ValueError("model_name 不能为空")

        self.model_name = model_name
        self.task_id = task_id or "default_task"
        models_config = get_model_config().get("task", {})
        if model_name not in models_config:
            raise ValueError(f"配置中找不到 task 模型 '{model_name}'")
        model_info = models_config[model_name]
        api_keys = model_info.get("api_keys") or [model_info.get("api_key")]
        valid_keys = [k for k in api_keys if k and k.strip()]
        self.base_url = model_info.get("base_url")

        self.api_key = key_manager.allocate_key(valid_keys, recovered_key_prefix)
        self.key_prefix = self.api_key[:15]

        limits = model_info.get("limits", {})
        max_concurrency = limits.get("concurrency", 1)
        self.semaphore = get_key_semaphore(self.api_key, max_concurrency)

        self._client = LLMClient(api_key=self.api_key, base_url=self.base_url)

        log(
            f"🔗 任务 {self.task_id} 锁定模型 {self.model_name}，绑定 API Key: {self.key_prefix}..."
        )

    def chat(self, messages: list, tools: list = None, **kwargs):
        """仅做透传，增加无阻塞的内存记账功能，支持流式调用拦截"""
        start_time = time.time()

        # 如果是流式请求，确保开启 usage 包含选项（OpenAI 最新规范）
        is_stream = kwargs.get("stream", False)
        if is_stream and "stream_options" not in kwargs:
            kwargs["stream_options"] = {"include_usage": True}

        response = self._client.execute_chat(
            model_name=self.model_name,
            messages=messages,
            task_id=self.task_id,
            semaphore=self.semaphore,
            tools=tools,
            **kwargs,
        )

        # ------------------ 辅助函数：打印缓存命中率 ------------------
        def _log_cache_debug(final_usage):
            if final_usage:
                p_details = getattr(final_usage, "prompt_tokens_details", None)
                cached_tokens = (
                    getattr(p_details, "cached_tokens", 0) if p_details else 0
                )
                total_prompt = getattr(final_usage, "prompt_tokens", 0)
                missed_tokens = total_prompt - cached_tokens
                hit_rate = (
                    (cached_tokens / total_prompt * 100) if total_prompt > 0 else 0
                )
                log(
                    f"📊 [Cache Debug] Task: {self.task_id} | Total Prompt: {total_prompt} | Hit: {cached_tokens} ({hit_rate:.1f}%) | Miss: {missed_tokens}"
                )

        # --------------------------------------------------------------

        if is_stream:
            # 包装生成器，拦截最后一个 chunk 的 usage
            def _stream_generator():
                final_usage = None
                for chunk in response:
                    if hasattr(chunk, "usage") and chunk.usage:
                        final_usage = chunk.usage
                    yield chunk

                duration = time.time() - start_time
                _log_cache_debug(final_usage)  # 打印流式缓存
                usage_tracer.record(
                    model_name=self.model_name,
                    api_key=self.api_key,
                    usage=final_usage,
                    duration=duration,
                )

            return _stream_generator()
        else:
            # 非流式，正常处理
            duration = time.time() - start_time
            usage = getattr(response, "usage", None)
            _log_cache_debug(usage)  # 打印非流式缓存
            usage_tracer.record(
                model_name=self.model_name,
                api_key=self.api_key,
                usage=usage,
                duration=duration,
            )
            return response

    def unbind(self):
        """释放资源"""
        if hasattr(self, "api_key") and self.api_key:
            key_manager.release_key(self.api_key)
            log(f"🔓 任务 {self.task_id} 已释放 API Key: {self.key_prefix}")

    def bind_task(self, task_id: str, task_name: str = None):
        """绑定任务 ID，用于日志追踪"""
        self.task_id = task_id
        if task_name:
            self.task_id = f"{task_name}_{task_id}"
        return self


class AgentModel(Model):
    """全局 Agent 的专属大模型客户端，从 main 字段读取唯一 API"""

    def __init__(self, task_id: str = None):
        from src.utils.config import get_agent_model

        model_name = get_agent_model()
        model_cfg = get_model_config().get("main", {}).get(model_name, {})

        self.model_name = model_name
        self.task_id = task_id or "default_task"
        self.base_url = model_cfg.get("base_url")
        self.api_key = model_cfg.get("api_key")

        if not self.api_key:
            api_keys = model_cfg.get("api_keys") or []
            valid_keys = [k for k in api_keys if k and k.strip()]
            if not valid_keys:
                raise ValueError("Agent 专属模型缺少有效的 api-key 配置")
            self.api_key = valid_keys[0]

        if not self.base_url or not self.api_key:
            raise ValueError("Agent 专属模型配置缺失")

        self.key_prefix = self.api_key[:15]

        limits = model_cfg.get("limits", {})
        max_concurrency = limits.get("concurrency", 1)
        self.semaphore = get_key_semaphore(self.api_key, max_concurrency)

        self._client = LLMClient(api_key=self.api_key, base_url=self.base_url)

        log(
            f"🤖 全局 Agent 锁定模型 {self.model_name}，使用专属 API Key: {self.key_prefix}..."
        )

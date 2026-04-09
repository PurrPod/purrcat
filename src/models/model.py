import threading
import time
import queue
from concurrent.futures import Future
import traceback

import httpx
from openai import OpenAI, RateLimitError, APIError
from src.utils.config import get_models_config

MODEL_POOL = []


class LLMDispatcher:
    """
    全局大模型调度中转站（单例）
    负责管理所有的模型 API-Key 专属消费线程，并实现基于 task_id 的一致性哈希路由（会话保持）
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LLMDispatcher, cls).__new__(cls)
                cls._instance.model_workers = {}  # {model_name: [Worker1, Worker2, ...]}
                cls._instance.task_bindings = {}  # {task_id: Worker}
                cls._instance.initialized_models = set()
            return cls._instance

    def init_model(self, model_name: str):
        with self._lock:
            if model_name in self.initialized_models:
                return

            models_config = get_models_config()
            if model_name not in models_config:
                raise ValueError(f"配置中找不到模型 '{model_name}'！请检查 config.yaml")

            model_info = models_config[model_name]
            api_keys = model_info.get("api_keys")
            if not api_keys:
                api_keys = [model_info.get("api_key")]

            valid_api_keys = [key for key in api_keys if key and key.strip()]
            if not valid_api_keys:
                raise ValueError(f"模型 '{model_name}' 没有有效的 api-key 配置！")

            base_url = model_info.get("base_url")
            if not base_url:
                raise ValueError(f"模型 '{model_name}' 缺少 'base_url' 配置！")

            # 为该模型创建专属的 Worker 列表
            self.model_workers[model_name] = []

            for idx, api_key in enumerate(valid_api_keys):
                # 【关键改动 1】: 每个 Worker 拥有自己独立的私有队列，不再吃“大锅饭”
                worker_queue = queue.Queue()
                worker = APIKeyWorker(model_name, api_key, base_url, worker_queue, idx)
                worker.daemon = True
                worker.start()
                self.model_workers[model_name].append(worker)

            self.initialized_models.add(model_name)

    def submit(self, model_name: str, task_id: str, kwargs: dict) -> Future:
        """接收任务，根据 task_id 分配到绑定的 Worker 私有队列中"""
        self.init_model(model_name)
        future = Future()

        with self._lock:
            workers = self.model_workers[model_name]

            # 【关键改动 2】: 会话保持与负载均衡
            if task_id and task_id in self.task_bindings:
                # 1. 之前绑定过，继续使用同一个 Worker（保证 KV Cache 命中）
                target_worker = self.task_bindings[task_id]
            else:
                # 2. 全新任务，寻找当前最闲的 Worker（队列积压最少的）
                target_worker = min(workers, key=lambda w: w.work_queue.qsize())
                # 如果有 task_id，则记录绑定关系
                if task_id:
                    self.task_bindings[task_id] = target_worker
                    print(
                        f"🔗 [调度分配] 任务 '{task_id}' 绑定到 Worker-{target_worker.worker_id} ({target_worker.masked_key})")

        # 将任务放入该 Worker 的专属私有队列，没空闲的自然会在这个队列里排队等待
        target_worker.work_queue.put((future, kwargs))
        return future

    def unbind_task(self, task_id: str):
        """释放 task_id 的绑定关系"""
        with self._lock:
            if task_id in self.task_bindings:
                worker = self.task_bindings.pop(task_id)
                print(f"🔓 [调度释放] 任务 '{task_id}' 已解除与 Worker-{worker.worker_id} 的绑定")


class APIKeyWorker(threading.Thread):
    """
    专属 API-Key 消费线程：处理请求并强制防限速休眠
    （带有增强的底层错误穿透与堆栈追踪能力）
    """

    def __init__(self, model_name: str, api_key: str, base_url: str, work_queue: queue.Queue, worker_id: int):
        super().__init__(name=f"Worker-{model_name}-{worker_id}")
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.work_queue = work_queue  # 现在这是该线程专属的队列
        self.worker_id = worker_id

        custom_http_client = httpx.Client(proxy=None, trust_env=False)
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=120.0,
            http_client=custom_http_client
        )
        self.masked_key = self.api_key[:8] + "..." if len(self.api_key) > 8 else self.api_key

    def run(self):
        print(f"🚀 [Worker启动] 模型: {self.model_name} | 专属线程已挂载 API-Key: {self.masked_key}")
        while True:
            # 阻塞等待属于自己的任务
            future, kwargs = self.work_queue.get()
            try:
                if future.set_running_or_notify_cancel():
                    result = self._process_with_retry(kwargs)
                    future.set_result(result)
            except Exception as e:
                print(f"\n🚨 [底层错误拦截] Worker {self.masked_key} 执行发生崩溃:")
                traceback.print_exc()
                future.set_exception(e)
            finally:
                self.work_queue.task_done()
                time.sleep(1.5)

    def _process_with_retry(self, kwargs: dict, max_retries: int = 4):
        base_delay = 1.0
        retries = 0
        last_exception = None
        while retries < max_retries:
            try:
                real_model_name = self.model_name.split(":")[-1] if ":" in self.model_name else self.model_name
                kwargs["model"] = real_model_name
                return self.client.chat.completions.create(**kwargs)
            except (RateLimitError, APIError) as e:
                error_msg = str(e).lower()
                # 遇到限速时，让这个专属线程原地等待。由于该任务绑定在这个线程上，
                # 它会跟着一起等，从而完美保住之前积累在服务器端的 KV Cache。
                if "rate limit" in error_msg or "429" in error_msg:
                    last_exception = e
                    retries += 1
                    print(
                        f"⚠️ [Worker {self.masked_key}] 触发限速限制，退避休眠 {base_delay:.1f}s... (重试 {retries}/{max_retries})")
                    time.sleep(base_delay)
                    base_delay *= 1.5
                else:
                    tb_str = traceback.format_exc()
                    full_error = f"API异常 [{type(e).__name__}]: {e}\n详细堆栈:\n{tb_str}"
                    raise Exception(full_error)
            except Exception as e:
                tb_str = traceback.format_exc()
                full_error = f"底层网络或系统异常 [{type(e).__name__}]: {e}\n详细堆栈:\n{tb_str}"
                raise Exception(full_error)

        tb_str = "".join(traceback.format_exception(type(last_exception), last_exception, last_exception.__traceback__))
        raise Exception(f"[Worker {self.masked_key}] 达到最大重试次数 ({max_retries})。最后一次错误为:\n{tb_str}")


class Model:
    """提供给业务层的极简大模型接口"""

    def __init__(self, name: str):
        if not name.strip():
            raise ValueError("模型名不能为空")
        self.name = name.strip()
        LLMDispatcher().init_model(self.name)
        self.desc = ""
        self.busy = False
        self.task_name = None
        self.task_id = None
        MODEL_POOL.append(self)

    def chat(self, messages: list, tools: list = None, response_format: dict = None, temperature: float = None):
        """最干净的统一调用入口，同步阻塞直到底层线程拿到结果"""
        kwargs = {"messages": messages}
        if tools: kwargs["tools"] = tools
        if response_format: kwargs["response_format"] = response_format
        if temperature is not None: kwargs["temperature"] = temperature

        # 【关键改动 3】: 将 self.task_id 传递给 Dispatcher 进行路由决策
        future = LLMDispatcher().submit(self.name, self.task_id, kwargs)
        return future.result()  # 阻塞等待专属线程返回结果

    def bind_task(self, task_id: str, task_name: str) -> None:
        self.task_id = task_id
        self.task_name = task_name

    def unbind_task(self) -> None:
        """任务结束时，主动通知调度器释放 Worker 占用"""
        if self.task_id:
            LLMDispatcher().unbind_task(self.task_id)
        self.task_id = None
        self.task_name = None

    def get_info(self):
        return f"[{self.name}]: {self.desc}"

    def __repr__(self) -> str:
        return f"Model(name={self.name!r}, description={self.desc!r})"
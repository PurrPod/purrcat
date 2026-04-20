import threading
import time
import queue
from concurrent.futures import Future
import traceback

import httpx
from openai import OpenAI, RateLimitError, APIError
from src.utils.config import get_models_config

MODEL_POOL = []


def calculate_tuning_params(rpm_limit: int, tpm_limit: int, max_concurrency: int):
    """自适应限流参数推导引擎"""
    # 1. 计算线程分配 (保证至少 1 个总并发)
    total_workers = max(1, max_concurrency)
    main_workers = 1
    light_workers = total_workers - 1

    # 2. 计算常规流控休眠时间 (Worker Sleep)
    # 公式: (60秒 * 总线程数) / RPM限制
    # 加入 10% 的安全冗余 (乘以 1.1)
    if rpm_limit > 0:
        base_sleep = (60.0 * total_workers / rpm_limit) * 1.1
    else:
        base_sleep = 1.5 # 默认兜底
    
    # 限制休眠时间上下限 (最少歇0.5秒防DDoS，最多歇60秒)
    worker_sleep_interval = max(0.5, min(base_sleep, 60.0))

    # 3. 计算 429 惩罚退避时间 (Base Delay)
    # 至少等待 1 个请求周期，兜底 2 秒
    base_delay = max(2.0, 60.0 / max(1, rpm_limit))

    # 4. 根据 TPM 动态计算轻量级任务阈值 (Light Threshold)
    # 假设每次请求最多吃掉 TPM 的 1/10，这里做一个粗略适配
    light_task_threshold = max(1000, tpm_limit // 50)

    return {
        "main_count": main_workers,
        "light_count": light_workers,
        "worker_sleep": worker_sleep_interval,
        "base_delay": base_delay,
        "light_threshold": light_task_threshold
    }


class LLMTask:
    def __init__(self, future, kwargs, light_threshold):
        self.future = future
        self.kwargs = kwargs
        
        msg_str = str(kwargs.get("messages", ""))
        input_estimate = len(msg_str) // 3
        output_estimate = kwargs.get("max_tokens", 1000)
        self.estimated_tokens = input_estimate + output_estimate
        
        self.is_light = self.estimated_tokens < light_threshold


class SmartTaskQueue:
    """终极版：带有状态感知与工作窃取 (Work Stealing) 的大小核队列"""
    def __init__(self, light_threshold=3000):
        self.heavy_tasks = []
        self.light_tasks = []
        self.cv = threading.Condition()
        
        self.idle_light_workers = 0  
        self.light_threshold = light_threshold


    def put(self, task: LLMTask):
        with self.cv:
            if task.is_light:
                self.light_tasks.append(task)
            else:
                self.heavy_tasks.append(task)
            self.cv.notify_all()


    def get_light(self) -> LLMTask:
        """小核 (Light Worker) 专用：只拿小任务"""
        with self.cv:
            while not self.light_tasks:
                self.idle_light_workers += 1  
                self.cv.wait()
                self.idle_light_workers -= 1  
            return self.light_tasks.pop(0)


    def get_main(self) -> LLMTask:
        """大核 (Main Worker) 专用：绝对优先大任务，条件触发偷小任务"""
        with self.cv:
            while True:
                if self.heavy_tasks:
                    return self.heavy_tasks.pop(0)
                
                if self.light_tasks and self.idle_light_workers == 0:
                    return self.light_tasks.pop(0)
                    
                self.cv.wait()


class LLMDispatcher:
    """
    全局大模型调度中转站（单例）
    负责管理所有的模型 API-Key 专属消费组，并实现基于 task_id 的一致性哈希路由（会话保持）
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LLMDispatcher, cls).__new__(cls)
                # 结构变更为：{ model_name: [ { "queue": smart_queue, "workers": [...] }, ... ] }
                cls._instance.model_groups = {}  
                cls._instance.task_bindings = {}  # {task_id: target_group}
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
            api_keys = model_info.get("api_keys") or [model_info.get("api_key")]
            valid_api_keys = [key for key in api_keys if key and key.strip()]
            
            if not valid_api_keys:
                raise ValueError(f"模型 '{model_name}' 没有有效的 api-key 配置！")
            base_url = model_info.get("base_url")
            if not base_url:
                raise ValueError(f"模型 '{model_name}' 缺少 'base_url' 配置！")

            # 获取用户配置的参数 (假设你在 config.yaml 里加了 limits 字段)
            limits = model_info.get("limits", {})
            
            # 【修改点】：将默认并发修改为 1，并配合相对保守的安全速率
            rpm = limits.get("rpm", 60)          # 默认 60 RPM (够单核全速跑了)
            tpm = limits.get("tpm", 100000)      # 默认 10 万 TPM
            concurrency = limits.get("concurrency", 1) # 默认 1 并发（1大核，0小核）

            # 调用引擎推算最佳参数！
            tuning = calculate_tuning_params(rpm, tpm, concurrency)

            self.model_groups[model_name] = []

            # 为【每个】 API-Key 创建独立的并发集群
            for idx, api_key in enumerate(valid_api_keys):
                # 每个 API-Key 拥有自己专属的智能队列，使用动态计算的轻量级任务阈值
                key_queue = SmartTaskQueue(light_threshold=tuning["light_threshold"])
                workers = []

                # 启动 1 个主核
                main_worker = APIKeyWorker(
                    model_name, api_key, base_url, key_queue,
                    worker_id=idx, is_main=True,
                    sleep_interval=tuning["worker_sleep"],
                    base_delay=tuning["base_delay"]
                )
                main_worker.daemon = True
                main_worker.start()
                workers.append(main_worker)

                # 根据推算结果，启动 N 个小核
                for i in range(tuning["light_count"]):
                    light_worker = APIKeyWorker(
                        model_name, api_key, base_url, key_queue,
                        worker_id=f"{idx}_L{i}", is_main=False,
                        sleep_interval=tuning["worker_sleep"],
                        base_delay=tuning["base_delay"]
                    )
                    light_worker.daemon = True
                    light_worker.start()
                    workers.append(light_worker)

                # 将整个群组存入映射表
                self.model_groups[model_name].append({
                    "api_key_id": idx,
                    "queue": key_queue,
                    "workers": workers
                })

            self.initialized_models.add(model_name)

    def submit(self, model_name: str, task_id: str, kwargs: dict) -> Future:
        """接收任务，根据 task_id 分配到绑定的群组队列中"""
        self.init_model(model_name)
        future = Future()

        with self._lock:
            groups = self.model_groups[model_name]

            # 基于群组进行会话保持绑定
            if task_id and task_id in self.task_bindings:
                target_group = self.task_bindings[task_id]
            else:
                # 寻找当前任务积压最少的群组 (大任务 + 小任务总数)
                target_group = min(groups, key=lambda g: len(g["queue"].heavy_tasks) + len(g["queue"].light_tasks))
                if task_id:
                    self.task_bindings[task_id] = target_group
                    print(f"🔗 [调度分配] 任务 '{task_id}' 绑定到 Key群组-{target_group['api_key_id']}")

        # 创建任务时传递轻量级任务阈值
        task = LLMTask(future, kwargs, target_group["queue"].light_threshold)
        # 放进该 Key 专属的队列，而不是全局队列
        target_group["queue"].put(task)
        return future

    def unbind_task(self, task_id: str):
        """释放 task_id 的绑定关系"""
        with self._lock:
            if task_id in self.task_bindings:
                group = self.task_bindings.pop(task_id)
                print(f"🔓 [调度释放] 任务 '{task_id}' 已解除与 Key群组-{group['api_key_id']} 的绑定")


class APIKeyWorker(threading.Thread):
    """
    专属 API-Key 消费线程：处理请求并强制防限速休眠
    （带有增强的底层错误穿透与堆栈追踪能力）
    """

    def __init__(self, model_name: str, api_key: str, base_url: str, smart_queue: SmartTaskQueue, worker_id: int, is_main: bool, sleep_interval: float = 1.5, base_delay: float = 2.0):
        super().__init__(name=f"Worker-{model_name}-{worker_id}")
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.smart_queue = smart_queue
        self.worker_id = worker_id
        self.worker_type = "main" if is_main else "light"
        self.sleep_interval = sleep_interval
        self.base_delay = base_delay

        custom_http_client = httpx.Client(proxy=None, trust_env=False)
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=120.0,
            http_client=custom_http_client
        )
        self.masked_key = self.api_key[:8] + "..." if len(self.api_key) > 8 else self.api_key

    def run(self):
        print(f"🚀 [{self.worker_type.upper()}核心启动] 模型: {self.model_name} | Key: {self.masked_key}")
        while True:
            if self.worker_type == "main":
                llm_task = self.smart_queue.get_main()
            else:
                llm_task = self.smart_queue.get_light()
            
            future, kwargs = llm_task.future, llm_task.kwargs
            
            try:
                if future.set_running_or_notify_cancel():
                    result = self._process_with_retry(kwargs)
                    future.set_result(result)
            except Exception as e:
                if not str(e).startswith(("API Error", "System Error", "CallFailed")):
                    print(f"\n🚨 [Worker线程意外崩溃] {self.masked_key}:")
                    traceback.print_exc()
                
                future.set_exception(e)
            finally:
                # 使用动态计算的常规休眠时间平滑 RPM
                time.sleep(self.sleep_interval)

    def _process_with_retry(self, kwargs: dict, max_retries: int = 5):
        current_delay = self.base_delay
        retries = 0
        last_exception = None
        while retries < max_retries:
            try:
                real_model_name = self.model_name.split(":")[-1] if ":" in self.model_name else self.model_name
                kwargs["model"] = real_model_name
                return self.client.chat.completions.create(**kwargs)
            except (RateLimitError, APIError) as e:
                error_msg = str(e).lower()
                # 遇到限速时休眠
                if "rate limit" in error_msg or "429" in error_msg:
                    last_exception = e
                    retries += 1
                    print(
                        f"⚠️ [Worker {self.masked_key}] 触发限速限制，退避休眠 {current_delay:.1f}s... (重试 {retries}/{max_retries})")
                    time.sleep(current_delay)
                    current_delay *= 2.0
                else:
                    # 非限速 API 错误：控制台打堆栈，对外抛出精简文本
                    print(f"\n🚨 [Worker {self.masked_key}] 非限速 API 异常:")
                    traceback.print_exc()
                    # 提取错误类型和第一行简要信息
                    short_msg = str(e).split('\n')[0]
                    raise Exception(f"API Error ({type(e).__name__}): {short_msg}")
            except Exception as e:
                # 底层系统错误：控制台打堆栈，对外抛出精简文本
                print(f"\n🚨 [Worker {self.masked_key}] 底层网络或系统异常:")
                traceback.print_exc()
                short_msg = str(e).split('\n')[0]
                raise Exception(f"System Error ({type(e).__name__}): {short_msg}")

        # 超过最大重试次数：控制台打印最后一次死掉的堆栈
        print(f"\n❌ [Worker {self.masked_key}] 达到最大重试次数 ({max_retries})，最后一次错误如下:")
        if last_exception:
            traceback.print_exception(type(last_exception), last_exception, last_exception.__traceback__)
            
        # 对外抛出最简单的总结
        error_name = type(last_exception).__name__ if last_exception else "UnknownError"
        short_msg = str(last_exception).split('\n')[0] if last_exception else "No exception info."
        raise Exception(f"CallFailed: Max retries ({max_retries}) exceeded. Last Error: {error_name} - {short_msg}")


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

        future = LLMDispatcher().submit(self.name, self.task_id, kwargs)
        return future.result()

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
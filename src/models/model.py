import json
import os
import threading

from openai import OpenAI
from src.utils.config import get_models_config

MODEL_POOL = []

class Model:
    def __init__(
        self,
        name: str,
        config_path: str = None,
    ):
        if not name.strip():
            raise ValueError("模型名（name）不能为空")
        self.name = name.strip()

        # 使用新的配置模块获取模型配置
        models_config = get_models_config()
        
        if self.name not in models_config:
            raise ValueError(f"Configuration for core '{self.name}' not found in config.yaml!")
        model_info = models_config[self.name]

        api_keys = model_info.get("api_keys")
        if not api_keys:
            api_key = model_info.get("api_key")
            if not api_key:
                raise ValueError(f"Core '{self.name}' is missing 'api_key' or 'api_keys' configuration!")
            api_keys = [api_key]
        
        base_url = model_info.get("base_url")
        if not base_url:
            raise ValueError(f"Core '{self.name}' is missing 'base_url' configuration!")
        
        self.api_keys = api_keys
        self.base_url = base_url
        self.current_index = 0
        self._lock = threading.Lock()
        
        # 初始化 client
        self.client = self._create_client()
        self.desc = ""
        self.busy = False
        self.task_name = None
        self.task_id = None
        MODEL_POOL.append(self)
    
    def _create_client(self):
        """创建 OpenAI client（使用当前轮询指针指向的 api_key）"""
        current_api_key = self.api_keys[self.current_index % len(self.api_keys)]
        return OpenAI(api_key=current_api_key, base_url=self.base_url)
    
    def rotate_api_key(self):
        """轮询到下一个 api_key（当遇到限速时调用）"""
        with self._lock:
            self.current_index = (self.current_index + 1) % len(self.api_keys)
            self.client = self._create_client()
            current_api_key = self.api_keys[self.current_index]
            # 只打印 key 的前 8 个字符，避免泄露
            masked_key = current_api_key[:8] + "..." if len(current_api_key) > 8 else current_api_key
            print(f"🔄 [Model {self.name}] 轮询到新 api-key: {masked_key}，索引: {self.current_index}/{len(self.api_keys)}")
    
    def get_current_api_key_masked(self):
        """获取当前 api-key 的脱敏版本（用于日志）"""
        current_api_key = self.api_keys[self.current_index % len(self.api_keys)]
        return current_api_key[:8] + "..." if len(current_api_key) > 8 else current_api_key

    def bind_task(self, task_id: str, task_name: str) -> None:
        self.task_id = task_id
        self.task_name = task_name

    def unbind_task(self) -> None:
        self.task_id = None
        self.task_name = None

    def get_info(self):
        return f"[{self.name}]: {self.desc}"

    def __repr__(self) -> str:
        return (
            f"Model(name={self.name!r}, description={self.desc!r}"
        )

def add_model_to_config(model_name, api_key, base_url, desc="LLM", config_path=None):
    """添加新模型到配置（使用 config.yaml）"""
    from src.utils.config import add_model_to_config as _add_model
    return _add_model(model_name, api_key, base_url, desc)

def remove_model_from_config(model_name, config_path=None):
    """从配置中删除模型（使用 config.yaml）"""
    from src.utils.config import remove_model_from_config as _remove_model
    return _remove_model(model_name)


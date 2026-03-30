import json
import os

from openai import OpenAI
from src.utils.config import get_models_config

MODEL_POOL = [
    {"model_name":"openai:deepseek-chat", "state":"idle"}
]

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
        api_key = model_info.get("api_key")
        base_url = model_info.get("base_url")
        if not api_key:
            raise ValueError(f"Core '{self.name}' is missing the 'api_key' configuration!")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.desc = ""
        self.busy = False
        self.task_name = None
        self.task_id = None
        MODEL_POOL.append(self)

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


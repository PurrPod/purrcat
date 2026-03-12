import json
import os

from openai import OpenAI

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

        if config_path is None:
            with open("data/config/config.json", "r", encoding="utf-8") as f:
                main_config = json.load(f)
            config_path = main_config["model_config"]


        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}. Please create it.")
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        models_config = config.get("models", {})
        if self.name not in models_config:
            raise ValueError(f"Configuration for core '{self.name}' not found in {config_path}!")
        model_info = models_config[self.name]
        api_key = model_info.get("api_key")
        base_url = model_info.get("base_url")
        if not api_key:
            raise ValueError(f"Core '{self.name}' is missing the 'api_key' configuration!")
        self.client = OpenAI(api_key=api_key, base_url=base_url)


        self.desc = config.get("description")
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

def add_model_to_config(model_name,api_key,base_url,desc="LLM",config_path="data/config/model_config.json"):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            config[model_name] = {"description":desc, "api_key": api_key, "base_url": base_url}
            f.write(json.dumps(config))
    except Exception as e:
        return False
    return True

def remove_model_from_config(model_name, config_path="data/config/model_config.json"):
    try:
        with open(config_path, "r+", encoding="utf-8") as f:
            config = json.load(f)
            if "models" in config and model_name in config["models"]:
                del config["models"][model_name]
                f.seek(0)
                json.dump(config, f, indent=4)
                f.truncate()
            else:
                return False
    except Exception as e:
        return False
    return True


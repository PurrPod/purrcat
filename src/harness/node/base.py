import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


def _format_result(result_data) -> str:
    if isinstance(result_data, str):
        try:
            parsed = json.loads(result_data)
            if "content" in parsed and "timestamp" in parsed:
                return result_data
            else:
                result_data = parsed
        except json.JSONDecodeError:
            pass

    finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(result_data, dict):
        result_data["timestamp"] = finish_time
        return json.dumps(result_data, ensure_ascii=False)

    return json.dumps(
        {"content": str(result_data), "timestamp": finish_time}, ensure_ascii=False
    )


class BaseNode:
    def __init__(self, node_id: str, config: dict):
        self.node_id = node_id
        self.config = config
        self.module_path = sys.modules[self.__module__].__file__
        self.node_dir = os.path.dirname(self.module_path)

        self.metadata = self._load_metadata()
        self.task_done_info = self.config.get(
            "task_done_info", self.metadata.get("task_done_info", {})
        )

    def _load_metadata(self) -> dict:
        base_path = Path(self.node_dir)
        metadata = {}
        try:
            json_path = base_path / "metadata.json"
            if json_path.exists():
                with open(json_path, "r", encoding="utf-8") as f:
                    json_data = json.load(f)
                    if isinstance(json_data, dict):
                        metadata.update(json_data)
        except Exception as e:
            print(
                f"⚠️ [元数据加载警告] 节点 {self.__class__.__module__} 加载配置出错: {e}"
            )
        return metadata

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """由子类实现的具体执行逻辑，必须返回字典作为向外投递的包裹"""
        raise NotImplementedError

    def log(self, context: Any, log_type: str, content: str, node_id: str = None):
        nid = node_id or self.node_id
        if hasattr(context, "log"):
            context.log(log_type, content, nid)
        else:
            print(f"[{log_type}] (Node: {nid}) {content}")

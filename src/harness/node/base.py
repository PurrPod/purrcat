from typing import Dict, Any, List


class BaseNode:
    def __init__(self, node_id: str, config: dict):
        self.node_id = node_id
        self.config = config
        self.outputs: Dict[str, Any] = {}

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: List[str], context: Any) -> Dict[str, Any]:
        """由子类实现的具体执行逻辑，增加 context 参数"""
        raise NotImplementedError

    def inject_force_push_to_messages(self, messages: List[Dict], force_push_msgs: List[str]) -> List[Dict]:
        """专供输入为 MessageList 类型的节点调用，拦截并注入人类指令"""
        if not force_push_msgs:
            return messages

        injected_messages = list(messages) if messages else []
        for msg in force_push_msgs:
            injected_messages.append({
                "role": "user",
                "content": f"[人类/系统强制干预] {msg}"
            })
        return injected_messages

    def log(self, context: Any, log_type: str, content: str, metadata: dict = None):
        """
        统一拦截并附加 node_id，这样日志面板可以精准定位是哪个节点发出的
        """
        if hasattr(context, "log_and_notify"):
            meta = metadata or {}
            meta["node_id"] = self.node_id
            context.log_and_notify(log_type, content, meta)
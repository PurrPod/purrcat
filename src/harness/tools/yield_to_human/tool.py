class Tool:
    def __init__(self, context=None):
        self.context = context

    def execute(self, arguments: dict) -> str:
        reason = arguments.get("reason", "需要人工干预")
        if self.context:
            self.context.state = "interrupted"
        return {"status": "waiting_for_human", "reason": reason}
class Tool:
    def __init__(self, context=None):
        self.context = context

    def execute(self, arguments: dict) -> str:
        summary = arguments.get("summary", "")
        if self.context:
            self.context.result = True
        return {"status": "success", "summary": summary}
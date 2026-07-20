import os
import yaml
import json
import subprocess


class HookHandler:
    def __init__(self, paradigm_path=None):
        self.paradigm_path = paradigm_path or "src/agent/system_rules/PARADIGM.yaml"
        self.config = {}
        self.hooks = {}
        self.load_config()

    def load_config(self, path=None):
        if path:
            self.paradigm_path = path
        if os.path.exists(self.paradigm_path):
            with open(self.paradigm_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}
            self.hooks = self.config.get("hooks", {})
        else:
            self.config, self.hooks = {}, {}

    def get_state(self):
        return {"paradigm_path": self.paradigm_path}

    def load_state(self, state):
        if not state:
            return
        self.paradigm_path = state.get("paradigm_path", self.paradigm_path)
        self.load_config()

    def dispatch_hook(self, hook_name, agent, epoch=0, **kwargs):
        if hook_name not in self.hooks:
            return []

        actions, results = self.hooks[hook_name], []
        for task in actions:
            for action_type, params in task.items():
                res = {"success": True}
                if action_type == "file_operation":
                    res = self._handle_file_operation(params, agent)
                elif action_type == "memo_injection":
                    res = self._handle_memo_injection(params, agent)
                elif action_type == "injection":
                    res = self._handle_injection(params, agent, epoch)
                elif action_type == "command_run":
                    res = self._handle_command_run(params, agent)
                elif action_type == "tool_use_check":
                    res = self._handle_tool_use_check(params, agent, **kwargs)
                if res:
                    results.append(res)
        return results

    def _should_trigger(self, params, epoch):
        delay = params.get("delay")
        interval = params.get("interval")

        if delay is not None and epoch != delay:
            return False
        if interval is not None and interval > 0 and epoch % interval != 0:
            return False
        return True

    def _handle_injection(self, params, agent, epoch):
        if not self._should_trigger(params, epoch):
            return {"success": True}
        return {
            "success": True,
            "inject_content": params.get("content", "")
        }

    def _handle_tool_use_check(self, params, agent, **kwargs):
        tool_name = params.get("name")
        if tool_name not in kwargs.get("used_tools", []):
            return {"success": False, "failed_prompt": params.get("failed_prompt", f"未检测到工具 {tool_name} 的合法调用记录")}
        else:
            success_prompt = params.get("successed_prompt")
            res = {"success": True}
            if success_prompt:
                res.update({"inject_content": success_prompt})
            return res

    def _handle_file_operation(self, params, agent):
        action = params.get("action")
        path = params.get("path", "")
        if action == "read":
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return {"success": True, "inject_content": f.read().strip()}
            return {"success": True, "inject_content": ""}
        elif action == "exist_check":
            if not os.path.exists(path):
                return {"success": False, "failed_prompt": params.get("failed_prompt", f"核心审计文件不存在: {path}")}
            return {"success": True}
        elif action == "write_in":
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(params.get("content", ""))
                return {"success": True}
            except Exception as e:
                return {"success": False, "failed_prompt": f"文件写入 I/O 异常: {e}"}
        return {"success": True}

    def _handle_memo_injection(self, params, agent):
        if hasattr(agent, 'memo') and agent.memo:
            content = f"【系统共享记忆缓存】\n{json.dumps(agent.memo, ensure_ascii=False, indent=2)}"
            return {"success": True, "inject_content": content}
        return {"success": True, "inject_content": ""}

    def _handle_command_run(self, params, agent):
        command = params.get("command", "")
        if command:
            subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"success": True}
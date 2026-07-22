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
            try:
                with open(self.paradigm_path, "r", encoding="utf-8") as f:
                    self.config = yaml.safe_load(f) or {}
                self.hooks = self.config.get("hooks", {})
            except Exception as e:
                print(f"[Warn] 解析 PARADIGM.yaml 发生异常: {e}")
        else:
            self.config, self.hooks = {}, {}

    def get_state(self):
        return {"paradigm_path": self.paradigm_path}

    def load_state(self, state):
        if not state:
            return
        self.paradigm_path = state.get("paradigm_path", self.paradigm_path)
        self.load_config()

    def _should_trigger(self, params, epoch):
        """处理 delay(仅一次) 和 interval(间隔多次) 逻辑"""
        delay = params.get("delay")
        interval = params.get("interval")

        if delay is not None and epoch != delay:
            return False
        if interval is not None and interval > 0 and epoch % interval != 0:
            return False
        return True

    def execute(self, stage_name, **kwargs):
        """
        统一暴露的路由解析接口
        参数输入: stage_name 和 **kwargs (需包含 epoch, used_tools 等上下文参数)
        """
        if stage_name not in self.hooks:
            return []

        epoch = kwargs.get("epoch", 0)
        actions = self.hooks[stage_name]
        results = []

        for task in actions:
            for action_type, params in task.items():
                if not self._should_trigger(params, epoch):
                    continue

                # 默认基准返回结构
                res = {"success": True, "inject_prompt": ""}

                # 路由分发
                if action_type == "file_operation":
                    res = self._file_operation(params, **kwargs)
                elif action_type == "injection":
                    res = self._injection(params, **kwargs)
                elif action_type in ["command_on", "command_run"]:  # 兼容旧版命名
                    res = self._command_on(params, **kwargs)
                elif action_type == "tool_use_check":
                    res = self._tool_use_check(params, **kwargs)
                elif action_type == "memo_injection":
                    # 兼容保留原有的记忆注入机制
                    res = self._memo_injection(params, **kwargs)

                if res:
                    results.append(res)

        # on_loop_end 重试次数限制：超过上限则强制放行
        if stage_name == "on_loop_end" and results:
            all_success = all(r.get("success") for r in results)
            if not all_success:
                retry_count = kwargs.get("loop_end_retry", 0)
                max_retry = self.config.get("loop_end_max_retry", 3)
                if retry_count >= max_retry:
                    print(f"[Warn] on_loop_end 已重试 {retry_count} 次，超过最大重试次数 {max_retry}，强制放行。")
                    return [{"success": True, "inject_prompt": ""}]

        return results

    # ==========================================
    # 工具函数区
    # ==========================================

    def _file_operation(self, params, **kwargs):
        path = params.get("path", "")
        action = params.get("action")
        content = params.get("content", "")
        failed_prompt = params.get("failed_prompt", f"文件操作 {action} 失败: {path}")

        res = {"success": True, "inject_prompt": ""}

        try:
            if action == "read":
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        file_content = f.read().strip()
                    res["inject_prompt"] = file_content
                    res["content"] = file_content  # 原样保留 content 字段，满足文档原意
                else:
                    res = {"success": False, "inject_prompt": failed_prompt}

            elif action == "exist_check":
                if not os.path.exists(path):
                    res = {"success": False, "inject_prompt": failed_prompt}

            elif action == "write_in":
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)

            elif action == "add_in":
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(content)

            elif action == "delete":
                if os.path.exists(path):
                    os.remove(path)
                else:
                    res = {"success": False, "inject_prompt": failed_prompt}
        except Exception as e:
            res = {"success": False, "inject_prompt": f"{failed_prompt} (Error: {e})"}

        return res

    def _injection(self, params, **kwargs):
        content = params.get("content", "")
        return {"success": True, "inject_prompt": content, "content": content}

    def _command_on(self, params, **kwargs):
        command = params.get("command", "")
        failed_prompt = params.get("failed_prompt", f"命令执行失败: {command}")
        return_log = params.get("return_log", False)

        if not command:
            return {"success": False, "inject_prompt": failed_prompt}

        try:
            if return_log:
                process = subprocess.run(command, shell=True, capture_output=True, text=True)
                if process.returncode == 0:
                    return {"success": True, "inject_prompt": process.stdout.strip()}
                else:
                    return {"success": False, "inject_prompt": process.stderr.strip() or failed_prompt}
            else:
                process = subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                process.wait()
                if process.returncode == 0:
                    return {"success": True, "inject_prompt": ""}
                else:
                    return {"success": False, "inject_prompt": failed_prompt}
        except Exception as e:
            return {"success": False, "inject_prompt": f"{failed_prompt} (Error: {e})"}

    def _tool_use_check(self, params, **kwargs):
        tool_name = params.get("name")
        used_tools = kwargs.get("used_tools", {})

        successed_prompt = params.get("successed_prompt", "")
        failed_prompt = params.get("failed_prompt", "")

        if tool_name not in used_tools:
            return {"success": False, "inject_prompt": failed_prompt}

        parameter_check = params.get("parameter_check")
        if parameter_check:
            args_list = used_tools.get(tool_name, [])
            matched = False
            for args in args_list:
                all_match = True
                for check_item in parameter_check:
                    for key, expected in check_item.items():
                        if args.get(key) != expected:
                            all_match = False
                            break
                    if not all_match:
                        break
                if all_match:
                    matched = True
                    break
            if not matched:
                return {"success": False, "inject_prompt": failed_prompt}

        return {"success": True, "inject_prompt": successed_prompt}

    def _memo_injection(self, params, **kwargs):
        agent = kwargs.get("agent")
        if agent and hasattr(agent, 'memo') and agent.memo:
            content = f"【系统共享记忆缓存】\n{json.dumps(agent.memo, ensure_ascii=False, indent=2)}"
            return {"success": True, "inject_prompt": content}
        return {"success": True, "inject_prompt": ""}

import datetime
import json
import ast
import os
import time
import uuid
import threading
import shutil

from src.agent.agent import add_message
from src.models.model import Model
from src.models.task import Task
from src.plugins.plugin_manager import get_plugin_tool_info

PROJECT_POOL = []
PROJECT_INSTANCES = {}  # 映射表：id -> Project 实例，用于随时调用类内方法

# 全局变量
dirty_projects = set()
set_lock = threading.Lock()  # 保护 set 的线程锁


def set_project_state(project_id, state):
    for p in PROJECT_POOL:
        if p["id"] == project_id:
            p["state"] = state
            p["updatedAt"] = datetime.datetime.now().isoformat()
            break
    if project_id in PROJECT_INSTANCES:
        PROJECT_INSTANCES[project_id].state = state
        PROJECT_INSTANCES[project_id].save_checkpoint()


def delete_project(project_id):
    global PROJECT_POOL
    checkpoint_dir = None

    if project_id in PROJECT_INSTANCES:
        instance = PROJECT_INSTANCES[project_id]
        checkpoint_dir = f"data/checkpoints/project/{instance.name}_{instance.creat_time}/"
        del PROJECT_INSTANCES[project_id]
    else:
        for p in PROJECT_POOL:
            if p.get("id") == project_id:
                name = p.get("name")
                creat_time = p.get("creat_time")
                if name and creat_time:
                    checkpoint_dir = f"data/checkpoints/project/{name}_{creat_time}/"
                break

    PROJECT_POOL = [p for p in PROJECT_POOL if p.get("id") != project_id]

    if checkpoint_dir and os.path.isdir(checkpoint_dir):
        try:
            shutil.rmtree(checkpoint_dir, ignore_errors=True)
        except Exception:
            pass


def kill_project(project_id):
    """全局方法：阶段性 Kill 指定的项目"""
    # 如果项目实例正在运行，则直接触发 kill 信号
    if project_id in PROJECT_INSTANCES:
        PROJECT_INSTANCES[project_id].kill()
        return True

    # 如果项目不在运行实例中，但仍存在于 PROJECT_POOL（例如后端重启后从 checkpoint 载入）
    # 允许前端仍然调用 stop 操作，让状态在界面上保持一致。
    for p in PROJECT_POOL:
        if p.get("id") == project_id:
            p["state"] = "killed"
            p["updatedAt"] = datetime.datetime.now().isoformat()
            return True

    return False


USER_QA_QUEUE = {}
AGENT_QA_QUEUE = {}


class Project:
    def __init__(
            self,
            name: str,
            prompt: str,
            core: str,
            check_mode: bool = False,
            refine_mode: bool = False,
            judge_mode: bool = False,
            sub_tasks=None,
            available_tools=None,
            available_workers=None,
            is_agent: bool = False,
            project_id=None):
        self.name = name
        self.ori_prompt = prompt
        self.prompt = prompt
        self.core = core
        self.creat_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.sub_tasks = sub_tasks
        self.available_tools = available_tools or []
        self.available_workers = available_workers or [self.core]
        self.check_mode = check_mode
        self.refine_mode = refine_mode
        self.judge_mode = judge_mode
        self.current_history = []
        self.stage_histories = {}
        self.task_story = ""
        self.is_agent = is_agent
        self.id = project_id or str(uuid.uuid4())
        self.state = "running"
        self._killed = False
        now_iso = datetime.datetime.now().isoformat()
        PROJECT_POOL.append({
            "name": self.name,
            "id": self.id,
            "state": self.state,
            "creat_time": self.creat_time,
            "core": self.core,
            "available_tools": self.available_tools,
            "available_workers": self.available_workers,
            "check_mode": self.check_mode,
            "refine_mode": self.refine_mode,
            "judge_mode": self.judge_mode,
            "is_agent": self.is_agent,
            "createdAt": now_iso,
            "updatedAt": now_iso,
        })# 固定元信息
        PROJECT_INSTANCES[self.id] = self

        # 1. 初始化时：推流文本类型的浅灰色卡片，显示用户的原始提示词
        self.log_and_notify(
            card_type="text",
            content=f"📝 用户的原始提示词：\n{self.ori_prompt}",
            metadata={"style": "light_gray"}
        )

    def kill(self):
        """类内方法：接收外部 kill 信号"""
        self._killed = True
        set_project_state(self.id, "killed")
        print(f"⚠️ [Project] 收到Kill指令，准备在下一节点挂起并中止项目 {self.id}...")

    def _check_kill(self):
        """检查中断标志，执行保存并抛出异常关闭当前线程"""
        if self._killed:
            self.save_checkpoint()  # 重点：保持原有的节点状态
            raise InterruptedError(f"项目 {self.id} 已被手动中止 (Kill)。")

    def send_to_core(self, prompt, is_stateless=False, response_format=None):
        self._check_kill()
        if ':' not in self.core:
            raise ValueError("The model name must include the provider prefix (e.g., openai:gpt-4o)")
        model_name = self.core.split(":")[-1]
        client = Model(self.core).client
        if isinstance(prompt, str):
            messages = self.current_history + [{"role": "user", "content": prompt}]
        elif isinstance(prompt, list):
            messages = prompt
        else:
            raise TypeError("Prompt must be a string or a list of messages.")
        try:
            kwargs = {
                "model": model_name,
                "messages": messages,
            }
            if response_format:
                kwargs["response_format"] = response_format
            response = client.chat.completions.create(**kwargs)
            result = response.choices[0].message.content
            if not is_stateless:
                if isinstance(prompt, str):
                    self.current_history.append({"role": "user", "content": prompt})
                elif isinstance(prompt, list):
                    self.current_history = prompt.copy()
                self.current_history.append({"role": "assistant", "content": result})

            return result
        except Exception as e:
            return f"Error: API call failed - {e}"

    def _ask_core_for_json(self, prompt, max_retries: int = 3):
        if isinstance(prompt, str):
            if "json" not in prompt.lower():
                prompt += "\nEnsure the output is a valid JSON object."
            messages = [{"role": "system", "content": prompt}]
        else:
            messages = prompt.copy()
        json_str = self.send_to_core(
            prompt=messages,
            is_stateless=True,
            response_format={"type": "json_object"}
        )
        print("| 😎:\n" + json_str)
        retry = 0
        while retry < max_retries:
            try:
                parsed_json = json.loads(json_str.strip())
                return parsed_json, json_str
            except json.JSONDecodeError as e:
                retry += 1
                if retry < max_retries:
                    error_msg = f"JSON parsing failed: {e}. Please check and output a valid JSON object."
                    retry_msgs = messages + [
                        {"role": "assistant", "content": json_str},
                        {"role": "user", "content": error_msg}
                    ]
                    json_str = self.send_to_core(
                        prompt=retry_msgs,
                        is_stateless=True,
                        response_format={"type": "json_object"}
                    )
                    print(f"(语法解析失败，第 {retry} 次重试):\n" + json_str)

        raise ValueError(f"经过 {max_retries} 次重试，仍无法获得有效的 JSON 格式。")

    def ask_user(self, questions):
        answers = {}
        q_list = []
        if isinstance(questions, list):
            q_list = [q for q in questions if q]
        elif isinstance(questions, dict):
            q_list = [q for k, q in questions.items() if k and q]
        if not q_list:
            return answers

        if self.is_agent:
            formatted_questions = "\n".join([f"{idx + 1}. {q}" for idx, q in enumerate(q_list)])
            prompt_to_agent = (
                f"项目执行挂起，需要您针对以下 {len(q_list)} 个问题提供决策或补充（请在一条消息中综合回答）：\n\n"
                f"{formatted_questions}"
            )
            AGENT_QA_QUEUE[self.id] = {
                "question": prompt_to_agent,
                "answer": None
            }
            notify_msg = f"🔔 [项目系统通知] 您的后台项目(ID: {self.id})已暂停，等待您回答 {len(q_list)} 个问题。请使用 check_pending_questions 工具查看，并使用 answer 工具直接输入您的回答。"
            print(f"\n[Agent通知] 发送通知: {notify_msg}")
            add_message({"type": "project_notice", "content": notify_msg})
            self.state = "waiting"
            set_project_state(self.id, self.state)
            while True:
                self._check_kill()
                if self.id in AGENT_QA_QUEUE and AGENT_QA_QUEUE[self.id].get("answer") is not None:
                    raw_ans = AGENT_QA_QUEUE[self.id]["answer"]
                    answers["Agent综合回复"] = raw_ans.strip()
                    del AGENT_QA_QUEUE[self.id]
                    self.state = "running"
                    set_project_state(self.id, self.state)
                    break
                time.sleep(1)
        else:
            print(f"等待用户在界面输入以下问题: {q_list}")
            self.state = "waiting"
            set_project_state(self.id, self.state)

            USER_QA_QUEUE[self.id] = {
                "questions": q_list,
                "answers": None
            }

            max_count = 1800
            count = 0
            while True:
                if count > max_count:
                    return answers
                self._check_kill()
                if self.id in USER_QA_QUEUE and USER_QA_QUEUE[self.id].get("answers") is not None:
                    answers = USER_QA_QUEUE[self.id]["answers"]
                    del USER_QA_QUEUE[self.id]
                    self.state = "running"
                    set_project_state(self.id, self.state)
                    break
                time.sleep(1)
        return answers

    def refine_prompt(self):
        sys_msg = (
                "[system] 你是一个提示词优化助手，用户会为你提供原始提示词。 "
                "你需要通过提问来获取优化这个原始提示词有关的细节 "
                "请用这样的JSON格式来列出你想问的所有问题: {\"questions\": [\"Question 1\", \"Question 2\"]}. \n"
                "这是用户的原始提示词:\n[User Original Prompt] " + self.prompt
        )
        data, raw_json_reply = self._ask_core_for_json(sys_msg)
        questions = data.get("questions", data)
        q_text = "\n".join(questions) if isinstance(questions, list) else str(questions)
        self.log_and_notify("text", f"🤖 Agent 提问：\n{q_text}", {"sender": "agent", "style": "gray"})
        self.log_and_notify("input", "✍️ 请提供您的补充要求", {"input_type": "text"})
        answers = self.ask_user(questions)
        context_messages = [
            {"role": "system", "content": sys_msg},
            {"role": "assistant", "content": raw_json_reply},
            {"role": "user", "content": (
                f"用户的回答如下：\n{answers}\n\n"
                f"请根据用户的初始需求和上述回答，输出最终优化好的、发给AI执行的【提示词(Prompt)】。\n"
                f"【警告】你的任务是“编写提示词”，绝不是“直接执行任务”！\n"
                f"请直接输出优化后的提示词文本，不要包含任何前缀、解释或多余的废话。"
            )}
        ]
        prompt = self.send_to_core(
            prompt=context_messages,
            is_stateless=True
        )
        return prompt

    def slice_tasks(self):
        sys_msg = (
            "你是一个任务切分助手，擅长把用户需求切分成数个子任务！！"
            "子任务会依次流经不同工人的手上，确保能承上启下完美继承，合理分配。\n"
            "请确保答案是这种纯JSON格式，不要包含Markdown或其他说明：\n"
            "{\"subtask1\": {\"title\": \"xxx\", \"desc\": \"xxx\", \"deliverable\": \"xxx\", \"worker\": \"xxx\", \"judger\": \"xxx\", \"available_tools\": [\"xxx\"]}, ...}\n"
            f"对于可用工人(worker/judger)，请必须从以下列表中严格选择：\n{self.available_workers}\n"
            f"对于可用工具(available_tools)，参考：\n{self.available_tools}\n"
            f"---\n[User Request] {self.prompt}\n"
            f"请开始切分子任务！"
        )
        max_retries = 3
        retry_count = 0
        current_messages = [{"role": "system", "content": sys_msg}]
        while retry_count < max_retries:
            sub_tasks, raw_json = self._ask_core_for_json(current_messages)
            is_valid = True
            error_details = []
            for key, value in sub_tasks.items():
                ai_worker = value.get("worker")
                if ai_worker and ai_worker not in self.available_workers:
                    is_valid = False
                    error_details.append(
                        f"任务 {key} 的 worker '{ai_worker}' 不在可用列表 {self.available_workers} 中。")
                ai_judger = value.get("judger")
                if ai_judger and ai_judger not in self.available_workers:
                    is_valid = False
                    error_details.append(
                        f"任务 {key} 的 judger '{ai_judger}' 不在可用列表 {self.available_workers} 中。")
                ai_tools = value.get("available_tools", [])
                if isinstance(ai_tools, list):
                    for tool in ai_tools:
                        if tool not in self.available_tools:
                            is_valid = False
                            error_details.append(f"任务 {key} 的工具 '{tool}' 不在可用列表 {self.available_tools} 中。")

            if is_valid:
                for key, value in sub_tasks.items():
                    if not value.get("worker"): value["worker"] = self.core
                    if not value.get("judger"): value["judger"] = self.core
                    if not value.get("tool"): value["tool"] = ["web", "filesystem"]
                self.sub_tasks = sub_tasks
                print(f"✅ 任务切分验证通过。")
                return
            else:
                retry_count += 1
                error_feedback = "\n".join(error_details)
                print(f"❌ 任务切分验证失败 (逻辑重修尝试 {retry_count}/{max_retries}):\n{error_feedback}")
                current_messages.append({"role": "assistant", "content": raw_json})
                current_messages.append({"role": "user","content": f"注意！你上一次生成的任务切分存在以下越界或错误：\n{error_feedback}\n请务必对照可用列表修正后，重新输出纯JSON格式。"})

        print("⚠️ 任务切分验证连续失败，将强制使用默认执行者，并忽略不合法的工具。")
        for key, value in sub_tasks.items():
            value["worker"] = self.core
            value["judger"] = self.core
            value["available_tools"] = [t for t in value.get("available_tools", []) if t in self.available_tools]
        self.sub_tasks = sub_tasks

    def run_tasks(self):
        task_histories_str = "[第1次执行任务集]\n" if not self.task_story else f"{self.task_story}\n[第2次执行任务集]\n"
        for task_key, task_detail in self.sub_tasks.items():
            if "task_id" not in task_detail:
                task_detail["task_id"] = str(uuid.uuid4())
            self.log_and_notify(
                card_type="task_status",
                content=f"⏳ 任务等待中: {task_detail.get('title', task_key)}",
                metadata={"task_id": task_detail["task_id"], "status": "wait"}
            )
        for task_key, task_detail in self.sub_tasks.items():
            self._check_kill()
            task_id = task_detail["task_id"]
            self.log_and_notify(
                card_type="task_status",
                content=f"⚙️ 正在执行: {task_detail.get('title', task_key)}",
                metadata={"task_id": task_id, "status": "running"}
            )
            print(f"Ready to execute: {task_key} -> {task_detail.get('title', '')}")
            system_prompt = f"[用户核心项目]{self.prompt}\n[项目子任务]{self.sub_tasks}\n[当前阶段]{task_detail}\n"
            single_task = Task(task_detail, judge_mode=self.judge_mode, system_prompt=system_prompt,
                               task_histories=task_histories_str, task_id=task_id)
            run_result = single_task.run_pipeline()
            self.current_history.append({task_key: str(run_result)})

            try:
                task_story = f"\n[{task_key} 完整执行日志]:\n"
                for step, res_str in enumerate(run_result):
                    res_dict = ast.literal_eval(res_str)
                    if "task_result" in res_dict:
                        status = "Worker交付" if res_dict["task_result"] else "Worker失败"
                        task_story += f"  - [{status}]: {res_dict.get('summary', res_dict.get('desc', '未知错误'))}\n"
                    elif "eval_result" in res_dict:
                        status = "质检通过" if res_dict["eval_result"] else "质检打回"
                        task_story += f"  - [{status}]: {res_dict.get('suggestion', '无修改建议')}\n"

                last_res = ast.literal_eval(run_result[-1])
                is_success = last_res.get("task_result", last_res.get("eval_result", False))

                task_histories_str += task_story
                self.task_story = task_histories_str

                if is_success:
                    self.log_and_notify("task_status", f"✅ 执行成功: {task_detail.get('title', task_key)}",
                                        {"task_id": task_id, "status": "success"})
                else:
                    self.log_and_notify("task_status", f"❌ 执行失败: {task_detail.get('title', task_key)}",
                                        {"task_id": task_id, "status": "failed"})
                    error_msg = last_res.get("summary",
                                             last_res.get("suggestion", last_res.get("desc", "未知子任务执行错误")))
                    return False, f"子任务 {task_key} 失败: {error_msg}\n完整历史: {task_story}"
            except Exception as e:
                self.log_and_notify("task_status", f"⚠️ 解析异常: {task_detail.get('title', task_key)}",
                                    {"task_id": task_id, "status": "failed"})
                return False, f"子任务 {task_key} 返回了不可解析的结果格式。报错: {e}"
        return True, "All tasks completed successfully."

    def run_pipeline(self):
        try:
            # 1. 需求优化阶段
            if self.refine_mode:
                self.log_and_notify("stage", "🪄 Refine Prompt", {"style": "dark_white"})
                prompt = self.refine_prompt()

                if self.check_mode:
                    # 推流包含按钮的 text 卡片，询问是否接受
                    self.log_and_notify(
                        card_type="text_with_action",
                        content=f"✨ 优化后的提示词如下：\n{prompt}\n🤔 是否接受？(请在后台回复 y/n)",
                        metadata={"actions": ["Accept", "Reject"]}
                    )
                    ans = self.ask_user(
                        [f"The current Prompt is as follows. Is it OK? (y/n)\n\n---\n\n{prompt}\n\n---\n\n"])
                    first_ans = list(ans.values())[0] if ans else 'n'
                    if 'y' in first_ans.lower():
                        self.prompt = prompt
                else:
                    self.prompt = prompt
                    self.log_and_notify("text", f"✅ 已优化提示词：\n{self.prompt}", {"style": "white"})

                self.save_history("refine_prompt", f"[原]: {self.ori_prompt} -> [优]: {self.prompt}")

            if not self.sub_tasks:
                self.log_and_notify("stage", "🧩 Slice Tasks", {"style": "white"})
                self.slice_tasks()

                self.log_and_notify("task_list", "📑 任务拆解完成", {"tasks": self.sub_tasks, "style": "gray"})
                self.save_history("slice_tasks", f"子任务组：{json.dumps(self.sub_tasks, ensure_ascii=False)}")

            self.log_and_notify("stage", "🚀 First Run Tasks", {"style": "white"})
            self.current_history = []
            success, msg = self.run_tasks()
            self.save_history("first_run_tasks", f"运行日志：\n{self.task_story}")

            if not success:
                self.log_and_notify("stage", "🔄 Re-Orchestrate", {"style": "white"})
                print(f"[项目遇到阻碍] {msg}\n正在请求核心模型重新编排任务...")

                worker_info = [Model(model).get_info() for model in self.available_workers]
                tool_info = [get_plugin_tool_info(self.available_tools)]
                available_worker_names = self.available_workers
                available_tool_names = self.available_tools

                clean_sub_tasks = {}
                for k, v in self.sub_tasks.items():
                    clean_task = v.copy()
                    clean_task.pop("task_id", None)
                    clean_sub_tasks[k] = clean_task

                retry_prompt = (
                    f"你是一个项目经理, 针对需求 '{self.prompt}', 原本将任务切分为: {json.dumps(clean_sub_tasks, ensure_ascii=False)}。\n"
                    f"执行发生中断，原因：{msg}\n"
                    f"请调整任务切分方式来解决中断。\n"
                    f"【重要警告】：返回的 sub_tasks 字典中，必须包含从头到尾完整的任务流（包括那些之前已经成功的任务），绝对不能只返回剩余的任务！\n"
                    f"返回纯JSON格式: {{\"retry\": bool, \"desc\": \"<简短说明>\", \"sub_tasks\": dict或null}}。\n"
                    f"对于可用工人(worker/judger)，请必须从以下列表中严格选择：\n{available_worker_names}\n"
                    f"对于可用工具(available_tools)，参考：\n{available_tool_names}\n"
                    f"{tool_info}"
                )

                max_retries = 3
                retry_count = 0
                current_messages = [{"role": "system", "content": retry_prompt}]

                try:
                    while retry_count < max_retries:
                        result_json, raw_json = self._ask_core_for_json(current_messages)

                        # 如果大模型判断无法重试，或者没返回任务，直接退出重试流
                        if not result_json.get("retry") or not result_json.get("sub_tasks"):
                            self.save_history("re_orchestrate",
                                              f"模型认为无法重试或未返回新任务集：{json.dumps(result_json, ensure_ascii=False)}")
                            msg = f"项目重试失败：模型认为无法通过重新编排解决问题。原错误：{msg}"
                            break

                        new_sub_tasks = result_json["sub_tasks"]
                        is_valid = True
                        error_details = []

                        for key, value in new_sub_tasks.items():
                            ai_worker = value.get("worker")
                            if ai_worker and ai_worker not in available_worker_names and ai_worker not in self.available_workers:
                                is_valid = False
                                error_details.append(
                                    f"任务 {key} 的 worker '{ai_worker}' 不在可用列表 {available_worker_names} 中。")

                            ai_judger = value.get("judger")
                            if ai_judger and ai_judger not in available_worker_names and ai_judger not in self.available_workers:
                                is_valid = False
                                error_details.append(
                                    f"任务 {key} 的 judger '{ai_judger}' 不在可用列表 {available_worker_names} 中。")

                            ai_tools = value.get("available_tools", [])
                            if isinstance(ai_tools, list):
                                for tool in ai_tools:
                                    if tool not in available_tool_names:
                                        is_valid = False
                                        error_details.append(
                                            f"任务 {key} 的工具 '{tool}' 不在可用列表 {available_tool_names} 中。")

                        if is_valid:
                            for key, value in new_sub_tasks.items():
                                if not value.get("worker"): value["worker"] = self.core
                                if not value.get("judger"): value["judger"] = self.core
                            for key, value in new_sub_tasks.items():
                                value["task_id"] = str(uuid.uuid4())
                            self.sub_tasks = new_sub_tasks
                            self.task_story += f"\n[retry]重新划分任务集：\n{json.dumps(self.sub_tasks, ensure_ascii=False)}\n"

                            self.log_and_notify("task_list", "📋 重新拆解任务完毕",
                                                {"tasks": self.sub_tasks, "style": "gray"})
                            self.save_history("re_orchestrate",
                                              f"重新编排成功：{json.dumps(result_json, ensure_ascii=False)}")

                            # 触发第二次运行
                            self.current_history = []
                            self.log_and_notify("stage", "🔁 Second Run Tasks", {"style": "white"})
                            success, retry_msg = self.run_tasks()
                            self.save_history("second_run_tasks",
                                              f"运行日志：{json.dumps(self.current_history, ensure_ascii=False)}")

                            if not success:
                                msg = f"项目重试后依然失败。最终错误：{retry_msg}"
                            break  # 执行完毕，跳出校验重试循环

                        else:
                            # 校验失败：打回要求大模型重写
                            retry_count += 1
                            error_feedback = "\n".join(error_details)
                            print(
                                f"❌ 重新编排任务切分验证失败 (逻辑重修尝试 {retry_count}/{max_retries}):\n{error_feedback}")

                            current_messages.append({"role": "assistant", "content": raw_json})
                            current_messages.append({
                                "role": "user",
                                "content": f"注意！你上一次生成的任务切分存在以下越界或错误：\n{error_feedback}\n请务必对照可用列表修正后，重新输出纯JSON格式。"
                            })

                    # 如果超过最大重试次数还没修正对
                    if retry_count >= max_retries:
                        msg = "🚫 项目重试失败：重新编排的任务连续多次未通过合法性校验。"
                        self.log_and_notify("error", msg, {"level": "error"})

                except Exception as e:
                    self.save_history("re_orchestrate", f"重新编排时解析异常：{e}")
                    self.log_and_notify("error", f"💥 重新编排失败: {e}", {"level": "error"})
                    success = False
                    msg = f"重新编排模型输出异常: {e}"

            # 5. 生成报告
            self.log_and_notify("stage", "📊 Run Summary", {"style": "white"})
            summary = self.run_summary(success, msg)

            # 推流 Markdown 最终报告渲染块
            self.log_and_notify("markdown", summary, {"title": "📑 项目最终执行报告"})
            self.save_history("summary", summary)
            if success:
                set_project_state(self.id, "completed")
            else:
                set_project_state(self.id, "error")
            return summary
        except InterruptedError as e:
            set_project_state(self.id, "killed")
            error_msg = f"⏸️ [项目挂起] 遇到意外中断: {e}。当前进度已在上一成功节点保存，可稍后通过 load_checkpoint 恢复执行。"
            self.log_and_notify("error", error_msg, {"level": "warning"})
            print(error_msg)
            set_project_state(self.id, self.state)
            return error_msg
        except Exception as e:
            set_project_state(self.id, "error")
            self.save_history("fatal_error", f"致命异常: {str(e)}")
            self.log_and_notify("error", f"🚨 系统致命异常: {str(e)}", {"level": "fatal"})
            return self.run_summary(False, f"致命异常: {str(e)}")

    def run_summary(self, success: bool, msg: str):
        """
        项目经理总览整个项目流程，生成 Markdown 格式的总结报告。
        重点包含对“失败与重新编排”的深度反思。
        """
        system_prompt = (
            "你是一个经验丰富的项目经理。请基于以下提供的项目执行完整历史，生成一份详尽的 Markdown 报告。\n"
            "报告必须包含以下三部分：\n"
            "1. **任务执行与波折记录**：描述初始的任务拆分方案及执行过程。**重点：**如果发生了任务失败和重新编排，必须详细对比前后任务切分方案的差异，并说明第一次失败的核心原因。\n"
            "2. **反思与经验积累**：分析项目执行中出现的成功经验和失败教训。特别要针对执行中遇到的阻碍，提出对未来类似项目的改进建议（例如：工具是否给错、任务是否切得太大等）。\n"
            "3. **交付物说明**：明确最终交付的内容（如代码、文档等），确保交付物描述完整。\n"
            "确保报告全面、清晰、专业。只提交报告内容，不要输出任何多余的寒暄废话。"
        )

        history_timeline = ""
        if "slice_tasks" in self.stage_histories:
            history_timeline += f"【初始任务划分方案】\n{self.stage_histories['slice_tasks']}\n\n"

        if "first_run_tasks" in self.stage_histories:
            history_timeline += f"【首次执行日志(可能包含失败)】\n{self.stage_histories['first_run_tasks']}\n\n"

        if "re_orchestrate" in self.stage_histories:
            history_timeline += f"【PM介入：失败分析与重新编排】\n{self.stage_histories['re_orchestrate']}\n\n"

        if "second_run_tasks" in self.stage_histories:
            history_timeline += f"【重排后二次执行日志】\n{self.stage_histories['second_run_tasks']}\n\n"

        user_content = (
            f"项目名称：{self.name}\n"
            f"原始需求：{self.ori_prompt}\n"
            f"优化后提示词：{self.prompt}\n"
            f"最终使用的子任务结构：{json.dumps(self.sub_tasks, ensure_ascii=False)}\n"
            f"============= 项目详细执行流 =============\n"
            f"{history_timeline}\n"
            f"============= 项目最终结果 =============\n"
            f"最终状态：{'成功' if success else '失败'}\n"
            f"状态详情：{msg}"
        )

        try:
            report = self.send_to_core(
                prompt=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                is_stateless=True
            )
        except Exception as e:
            report = f"生成报告时发生错误：{e}\n\n项目执行状态：{'成功' if success else '失败'}，消息：{msg}"

        return report

    def save_checkpoint(self):
        """将当前项目的所有状态序列化保存到本地"""
        checkpoint_dir = f"data/checkpoints/project/{self.name}_{self.creat_time}/"
        os.makedirs(checkpoint_dir, exist_ok=True)
        filepath = os.path.join(checkpoint_dir, f"checkpoint.json")
        state = self.__dict__.copy()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
        print(f"💾 [Checkpoint] 项目进度已自动存档至: {filepath}")

    @classmethod
    def load_checkpoint(cls, filepath: str):
        """类方法：从存档文件中恢复 Project 实例"""
        with open(filepath, 'r', encoding='utf-8') as f:
            state = json.load(f)
        project = cls(
            name=state.get("name"),
            prompt=state.get("ori_prompt"),
            core=state.get("core")
        )
        project.__dict__.update(state)
        print(f"🔄 [Checkpoint] 成功从 {filepath} 恢复项目状态，准备继续执行...")
        return project

    def save_history(self, stage_name: str, content: str):
        """记录关键节点信息留给总结报告，并触发自动存档方便断点续传"""
        self.stage_histories[stage_name] = content
        self.save_checkpoint()

    def log_and_notify(self, card_type: str, content: str, metadata: dict = None):
        """为前端专门准备的结构化执行日志数据"""
        # 修复：确保存放 log.jsonl 的父文件夹一定存在，避免由于系统未生成 checkpoint_dir 导致写文件闪退
        log_dir = f"data/checkpoints/project/{self.name}_{self.creat_time}/"
        os.makedirs(log_dir, exist_ok=True)

        # 增加前端要求的规范结构：card_type 和 metadata (带容错兜底)
        log_data = {
            "project_id": self.id,
            "timestamp": time.time(),
            "card_type": card_type,
            "content": content,
            "metadata": metadata or {}
        }

        with open(os.path.join(log_dir, "log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
            f.flush()

        with set_lock:
            dirty_projects.add(self.id)
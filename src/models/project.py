import datetime
import json
import ast
import os
import time
import uuid

from src.agent.agent import add_message
from src.models.model import Model
from src.models.task import Task
from src.plugins.plugin_manager import get_plugin_tool_info
PROJECT_POOL = [{"name":"xxx", "id":"xxx", "state":"running"},
                {"name":"xxx", "id":"xxx", "state":"completed"},
                {"name":"xxx", "id":"xxx", "state":"error"},
                {"name": "xxx", "id": "xxx", "state": "waiting"}]
PROJECT_INSTANCES = {}  # 映射表：id -> Project 实例，用于随时调用类内方法

def set_project_state(project_id, state):
    for p in PROJECT_POOL:
        if p["id"] == project_id:
            p["state"] = state
            break
    if project_id in PROJECT_INSTANCES:
        PROJECT_INSTANCES[project_id].state = state

def delete_project(project_id):
    global PROJECT_POOL
    PROJECT_POOL = [p for p in PROJECT_POOL if p["id"] != project_id]
    if project_id in PROJECT_INSTANCES:
        del PROJECT_INSTANCES[project_id]

def kill_project(project_id):
    """全局方法：阶段性 Kill 指定的项目"""
    if project_id in PROJECT_INSTANCES:
        PROJECT_INSTANCES[project_id].kill()
        return True
    return False

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
        self.available_workers = available_workers or []
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
        PROJECT_POOL.append({"name": self.name, "id": self.id, "state": self.state})
        PROJECT_INSTANCES[self.id] = self

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
        """
        向核心模型发送请求，统一的通信出口。
        """
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
        """
        利用原生的 JSON Mode 获取可靠的 JSON 数据。
        prompt 可以是字符串(sys_msg)，也可以是完整的 messages 列表。
        所有调用此方法的请求均被视为“辅助请求(is_stateless=True)”，不计入主线历史。
        """
        # 如果是字符串，包成 system message
        if isinstance(prompt, str):
            if "json" not in prompt.lower():
                prompt += "\nEnsure the output is a valid JSON object."
            messages = [{"role": "system", "content": prompt}]
        else:
            messages = prompt.copy() # 如果是列表，复制一份避免污染
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
        if self.is_agent:
            q_list = []
            if isinstance(questions, list):
                q_list = [q for q in questions if q]
            elif isinstance(questions, dict):
                q_list = [q for k, q in questions.items() if k and q]

            if not q_list:
                return answers

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
            add_message({"type": "project_notice","content": notify_msg})
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
            if isinstance(questions, list):
                for q in questions:
                    if q:
                        answers[q] = input(f"{q}\nYour answer: ")
            elif isinstance(questions, dict):
                for k, q in questions.items():
                    if k and q:
                        answers[q] = input(f"{q}\nYour answer: ")
        return answers
    def refine_prompt(self):
        sys_msg = (
                "[system] You are a prompt optimization assistant. The user will provide an original prompt, "
                "and you need to collect necessary details by asking questions to optimize it. "
                "Please list all questions at once in the following JSON format: {\"questions\": [\"Question 1\", \"Question 2\"]}. \n"
                "Here is the user's original prompt:\n[User Original Prompt] " + self.prompt
        )

        data, raw_json_reply = self._ask_core_for_json(sys_msg)
        questions = data.get("questions", data)
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
        worker_info = [Model(model).get_info() for model in self.available_workers]
        tool_info = [get_plugin_tool_info(self.available_tools)]
        available_worker_names = [m.split(':')[-1] if ':' in m else m for m in self.available_workers]
        available_tool_names = self.available_tools

        sys_msg = (
            "你是一个任务切分助手，擅长把用户需求切分成数个子任务！！"
            "子任务会依次流经不同工人的手上，确保能承上启下完美继承，合理分配。\n"
            "请确保答案是这种纯JSON格式，不要包含Markdown或其他说明：\n"
            "{\"subtask1\": {\"title\": \"xxx\", \"desc\": \"xxx\", \"deliverable\": \"xxx\", \"worker\": \"xxx\", \"judger\": \"xxx\", \"available_tools\": [\"xxx\"]}, ...}\n"
            f"对于可用工人(worker/judger)，请必须从以下列表中严格选择：\n{available_worker_names}\n"
            f"对于可用工具(available_tools)，参考：\n{tool_info}\n"
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
                            error_details.append(f"任务 {key} 的工具 '{tool}' 不在可用列表 {available_tool_names} 中。")

            if is_valid:
                for key, value in sub_tasks.items():
                    if not value.get("worker"): value["worker"] = self.core
                    if not value.get("judger"): value["judger"] = self.core
                self.sub_tasks = sub_tasks
                print(f"✅ 任务切分验证通过。")
                return
            else:
                retry_count += 1
                error_feedback = "\n".join(error_details)
                print(f"❌ 任务切分验证失败 (逻辑重修尝试 {retry_count}/{max_retries}):\n{error_feedback}")
                current_messages.append({"role": "assistant", "content": raw_json})
                current_messages.append({"role": "user",
                                         "content": f"注意！你上一次生成的任务切分存在以下越界或错误：\n{error_feedback}\n请务必对照可用列表修正后，重新输出纯JSON格式。"})

        print("⚠️ 任务切分验证连续失败，将强制使用默认执行者，并忽略不合法的工具。")
        for key, value in sub_tasks.items():
            value["worker"] = self.core
            value["judger"] = self.core
            valid_tools = [t for t in value.get("available_tools", []) if t in available_tool_names]
            value["available_tools"] = valid_tools
        self.sub_tasks = sub_tasks

    def run_tasks(self):
        """
        依次执行所有子任务。
        成功返回: (True, "All tasks completed successfully.")
        失败返回: (False, "错误详情信息")
        """
        task_histories_str = "[第1次执行任务集]\n" if not self.task_story else f"{self.task_story}\n[第2次执行任务集]\n"

        for task_key, task_detail in self.sub_tasks.items():
            self._check_kill()
            print(f"Ready to execute: {task_key} -> {task_detail.get('title', '')}")
            system_prompt = f"[用户核心项目]{self.prompt}\n[项目子任务]{self.sub_tasks}\n[当前阶段]{task_detail}\n"

            single_task = Task(task_detail, judge_mode=self.judge_mode, system_prompt=system_prompt,
                               task_histories=task_histories_str)
            run_result = single_task.run_pipeline()

            # 将每个任务的执行结果写入项目的 current_history
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

                if not is_success:
                    error_msg = last_res.get("summary",
                                             last_res.get("suggestion", last_res.get("desc", "未知子任务执行错误")))
                    return False, f"子任务 {task_key} 失败: {error_msg}\n完整历史: {task_story}"

            except Exception as e:
                return False, f"子任务 {task_key} 返回了不可解析的结果格式。报错: {e}"

        return True, "All tasks completed successfully."

    def run_pipeline(self):
        try:
            # 1. 需求优化阶段
            if self.refine_mode:
                prompt = self.refine_prompt()
                if self.check_mode:
                    ans = self.ask_user(
                        [f"The current Prompt is as follows. Is it OK? (y/n)\n\n---\n\n{prompt}\n\n---\n\n"])
                    first_ans = list(ans.values())[0] if ans else 'n'
                    if 'y' in first_ans.lower():
                        self.prompt = prompt
                else:
                    self.prompt = prompt
                self.save_history("refine_prompt", f"[原]: {self.ori_prompt} -> [优]: {self.prompt}")

            # 2. 任务切分阶段
            if not self.sub_tasks:
                self.slice_tasks()
                self.save_history("slice_tasks", f"子任务组：{json.dumps(self.sub_tasks, ensure_ascii=False)}")

            # 3. 第一次执行任务集
            self.current_history = []  # 开始执行前，重置主线对话历史
            success, msg = self.run_tasks()
            self.save_history("first_run_tasks", f"运行日志：\n{self.task_story}")

            # 4. 容错编排机制
            if not success:
                print(f"[项目遇到阻碍] {msg}\n正在请求核心模型重新编排任务...")
                worker_info = [Model(model).get_info() for model in self.available_workers]
                tool_info = [get_plugin_tool_info(self.available_tools)]

                retry_prompt = (
                    f"你是一个项目经理, 针对需求 '{self.prompt}', 将任务切分为: {self.sub_tasks}。\n"
                    f"执行发生中断，原因：{msg}\n"
                    f"请判断能否调整切分方式解决中断。返回纯JSON格式: {{\"retry\": bool, \"desc\": \"<简短说明>\", \"sub_tasks\": dict或null}}。\n"
                    f"Available Workers: {self.available_workers}\nTools: {self.available_tools}"
                    f"Worker_info: {worker_info}\nTool_info: {tool_info}"
                )

                try:
                    result_json, _ = self._ask_core_for_json(retry_prompt)
                    self.save_history("re_orchestrate", f"重新编排意见：{json.dumps(result_json, ensure_ascii=False)}")

                    if result_json.get("retry") and result_json.get("sub_tasks"):
                        self.sub_tasks = result_json["sub_tasks"]
                        self.task_story += f"\n[retry]重新划分任务集：\n{json.dumps(self.sub_tasks, ensure_ascii=False)}\n"

                        # 清空对话历史，给第二次执行一张白纸
                        self.current_history = []
                        success, retry_msg = self.run_tasks()
                        self.save_history("second_run_tasks",
                                          f"运行日志：{json.dumps(self.current_history, ensure_ascii=False)}")

                        if not success:
                            msg = f"项目重试后依然失败。最终错误：{retry_msg}"
                except Exception as e:
                    self.save_history("re_orchestrate", f"重新编排时解析异常：{e}")
                    success = False
                    msg = f"重新编排模型输出异常: {e}"

            # 5. 生成报告
            summary = self.run_summary(success, msg)
            if success:
                set_project_state(self.id, "completed")
            else:
                set_project_state(self.id, "error")
            return summary
        except InterruptedError as e:
            set_project_state(self.id, "killed")
            error_msg = f"⏸️ [项目挂起] 遇到意外中断: {e}。当前进度已在上一成功节点保存，可稍后通过 load_checkpoint 恢复执行。"
            print(error_msg)
            set_project_state(self.id, self.state)
            return error_msg
        except Exception as e:
            # ====== 新增：发生未知崩溃 ======
            set_project_state(self.id, "error")

            self.save_history("fatal_error", f"致命异常: {str(e)}")
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
        checkpoint_dir = f"data/checkpoints/{self.name}/"
        os.makedirs(checkpoint_dir, exist_ok=True)
        filepath = os.path.join(checkpoint_dir, f"{self.name}_{self.creat_time}.json")
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
        """记录关键节点信息，并触发自动存档"""
        self.stage_histories[stage_name] = content
        self.save_checkpoint()  # 自动存档点
import os

from src.harness.task import BaseTask

class MediaTask(BaseTask, expert_type="media", description="自媒体全工作流运营专家，账号参数已固定为：计算机类科普账号，请勿用此运营其它话题的内容"):
    def __init__(self, task_name, prompt, core, **kwargs):
        super().__init__(task_name, prompt, core)
        self.time_step = {
            "profile_push": False,
            "stage1": False,
        }
        self.workspace_dir = f"/agent_vm/media_task/{self.task_name}"
        os.makedirs(self.workspace_dir, exist_ok=True)

    def check_stage_file(self, filename):
        """通用检查函数：检查特定阶段的交付物是否存在"""
        file_path = os.path.join(self.workspace_dir, filename)
        return os.path.exists(file_path) and os.path.getsize(file_path) > 0

    def run(self):
        os.makedirs(self.workspace_dir, exist_ok=True)
        if not self.time_step["stage1"]:
            while not self.check_stage1():
                if not self.time_step["profile_push"]:
                    stage1_history = []
                    with open("data/profile.md","r",encoding="utf-8") as f:
                        profile_content = f.read()
                    stage1_history.append({"role":"system","content":f"你是一个自媒体账号运维专家，协助老板进行自媒体账号的运营，你需要根据账号参数来生产对应话题的爆款图文笔记。并调用适当的工具或skill进行你的工作。\n以下是你负责的账号的相关参数：\n{profile_content}"})
                    stage1 = f"""## 阶段 1：选题挖掘与爆款角度卡位
            
### 核心目标

拒绝盲目追热点，基于输入话题，筛选出「匹配账号人设、高爆款概率、低合规风险、强受众共鸣」的精准选题，完成爆款的核心卡位

### 融合后执行动作

1. 跨平台全量热点聚合：基于输入话题，全网抓取相关热点数据，覆盖微博 / 抖音 / B 站 / 小红书 / 知乎 / 百度热榜，不仅收集热度值，同步抓取热度增速、生命周期、受众讨论度、竞争烈度数据
2. 受众情绪与爆款角度匹配：针对话题相关内容，自动分析评论区 / 弹幕高赞内容，提炼核心共鸣点、争议点、新知点、痛点需求，匹配账号人设，锁定差异化爆款角度
3. 同赛道对标爆款拆解：针对话题相关的同赛道高赞内容，自动拆解核心选题逻辑、叙事结构、流量亮点，规避同质化竞争，找到差异化切入角度
4. 多维度选题生成与分级：输出 3-5 个可行的选题角度，每个角度标记「高流量 / 高风险 / 长生命周期 / 低竞争」标签，同时完成爆款概率量化评分（热度增速 + 受众匹配度 + 内容延展性 + 变现契合度），筛选 TOP2 最优选题

### 或许有用的skill(通过Fetch工具获取，并可以在沙盒环境中运行Bash来使用skill内置脚本)
运行内置脚本时可能会遇到环境配置问题，请按照技能手册一步步配置
```
baoyu-url-to-markdown
```

### 交付要求
在沙盒的/agent_vm/media_task/{self.task_name}/下生成一个热点话题与选题分析报告，命名为：hot_topic_choice.md
请确保自己交付的产物不含幻觉生成内容，必须是实打实通过调用工具并仔细分析出来的结果
任务完成后，调用task_done工具完成第一阶段的交付
"""
                    skill_content = self.fetch_skill_content("baoyu-url-to-markdown")
                    stage1_history.append({"role":"user","content":f"{stage1}\n\n以下是老板要求：{self.prompt}\n\n或许有用的skill：\n\n{skill_content}"})
                else:
                    self.time_step["profile_push"] = True
                    pass
                stage1_tools = self.get_stage1_tools()
                self.step_single_loop(stage1_history, stage1_tools)
        else:
            self.time_step["stage1"] = True
            pass





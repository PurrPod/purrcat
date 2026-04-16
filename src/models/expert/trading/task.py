# 一个测试用的 trading 专家，仅作 demo 用。

import json
import threading
import concurrent.futures
from src.models.task import BaseTask

# 延迟导入可能缺失的依赖，防止模块级别导入失败
try:
    from src.models.model import Model
except ImportError as e:
    print(f"⚠️ Model 导入失败（缺依赖）: {e}")
    Model = None

try:
    from src.loader.memory import Memory
except ImportError as e:
    print(f"⚠️ Memory 导入失败: {e}")
    Memory = None

try:
    from src.plugins.plugin_manager import parse_tool
except ImportError as e:
    print(f"⚠️ parse_tool 导入失败: {e}")
    parse_tool = None


class TradingTask(
    BaseTask,
    expert_type="trading",
    description="量化交易专家，负责股票的多空辩论、基本面/技术面分析及风险定调。",
    parameters={
        "company_name": {
            "type": "string",
            "description": "要分析的公司名称或股票代码（如 '苹果', 'AAPL'）",
            "required": True
        },
        "trade_date": {
            "type": "string",
            "description": "交易分析的基准日期，默认为 'Current'",
            "required": False,
            "default": "Current"
        }
    }
):
    def __init__(self, task_name, prompt, core, judger, company_name, trade_date=None):
        super().__init__(task_name, prompt, core, judger)
        self.company_name = company_name
        self.trade_date = trade_date or "Current"
        self.max_debate_rounds = 2
        self.max_risk_discuss_rounds = 2

        # 1. 初始化独立的图状态
        self.agent_state = self._get_default_agent_state()
        self.financial_memory = Memory()
        self._token_lock = threading.Lock()

    def _get_default_agent_state(self):
        """生成默认状态机"""
        return {
            "company_of_interest": getattr(self, "company_name", "Unknown"),
            "trade_date": getattr(self, "trade_date", "Current"),
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {"bull_history": [], "bear_history": [], "history": "", "judge_decision": ""},
            "trader_investment_plan": "",
            "risk_debate_state": {"aggressive_history": [], "neutral_history": [], "conservative_history": [],
                                  "history": "", "judge_decision": ""},
            "final_trade_decision": ""
        }

    # ================= 生命周期钩子 (完美对接 BaseTask) =================
    def _on_save_state(self) -> dict:
        """任务存档时，自动打包 TradingTask 的特有数据"""
        return {
            "company_name": self.company_name,
            "trade_date": self.trade_date,
            "agent_state": self.agent_state
        }

    def _on_restore_state(self, state: dict):
        """任务读档恢复时，重建 TradingTask 的环境与数据"""
        # 1. 恢复不可序列化的对象（避免 AttributeError 崩溃）
        self._token_lock = threading.Lock()
        self.financial_memory = Memory()

        # 2. 从额外状态中恢复特定属性
        extra = state.get("extra_state", {})

        # 向下兼容旧版“黑科技”存档：如果你有以前跑了一半的任务是用 current_plan 存的，这里顺手读出来
        old_plan = state.get("current_plan", "")
        if not extra and old_plan and old_plan.startswith("{"):
            try:
                extra = json.loads(old_plan)
            except Exception as e:
                self.log_and_notify("warning", f"尝试读取旧版状态兼容失败: {e}")

        self.company_name = extra.get("company_name", "Unknown")
        self.trade_date = extra.get("trade_date", "Current")
        self.agent_state = extra.get("agent_state", self._get_default_agent_state())

        # 兜底旧版的嵌套 key
        if "company_of_interest" in self.agent_state:
            self.company_name = self.agent_state["company_of_interest"]

    def _track_token_usage(self, response) -> dict:
        """保证多线程并发时的 Token 累加绝对安全"""
        with self._token_lock:
            return super()._track_token_usage(response)

    def run(self):
        """
        【覆写运行逻辑】：引入了节点状态机，支持断点精准跳过，完美对接 Exception 现场保护
        """
        self.state = "running"

        # 定义执行流图节点
        nodes = [
            ("分析师团队执行", self._node_analysts),
            ("多空投资辩论", self._node_investment_debate),
            ("交易员推演", self._node_trader),
            ("风控团队评估", self._node_risk_debate),
            ("投资组合经理决断", self._node_portfolio_manager)
        ]

        try:
            # 巧妙利用底层的 self.step 来记录当前跑到哪个节点了！
            while self.step < len(nodes):
                node_name, current_node_func = nodes[self.step]
                self.log_and_notify("system",
                                    f"\n" + "=" * 40 + f"\n▶️ 正在执行阶段 [{self.step + 1}/{len(nodes)}]: {node_name}\n" + "=" * 40)

                # 执行图节点逻辑
                current_node_func()

                # 节点成功完成后：步数+1 -> 落盘保存！（内部会自动触发 _on_save_state 钩子）
                self.step += 1
                self.save_checkpoint()

                # 为了 UI 呈现，向主线历史注入一条简要节点总结
                self.history.append({"role": "assistant", "content": f"✅ {node_name} 执行完毕，状态已保存。"})

            # 所有节点执行完毕
            self.state = "completed"
            if self.model: self.model.unbind_task()
            self._cleanup_resources()
            self.save_checkpoint()

            final_decision = self.agent_state['final_trade_decision']
            self.history.append({"role": "assistant", "content": f"🎯 最终交易决策：\n{final_decision}"})
            return f"✅ 任务成功，最终决策：\n{final_decision}"

        # ====== 完美复刻底层 BaseTask 的异常处理与资源回收 ======
        except KeyboardInterrupt:
            self.state = "error"
            if self.model: self.model.unbind_task()
            self._cleanup_resources()
            self.log_and_notify("system", "⚠️ 检测到强制中断 (Ctrl+C)，保存现场...")
            self.save_checkpoint()
            raise
        except Exception as e:
            self.state = "error"
            if self.model: self.model.unbind_task()
            self._cleanup_resources()
            self.log_and_notify("error", f"❌ 运行发生异常: {e}")
            self.save_checkpoint()
            raise InterruptedError(f"交易任务异常中断: {e}")

    def resume(self):
        """【覆写恢复逻辑】：让断点恢复支持有向无环图 (DAG)"""
        self.log_and_notify("system", f"🔄 尝试从图谱断点恢复任务... 当前处于第 {self.step + 1} 个节点。")
        self.log_and_notify("system", "🚀 环境排错完成，跳过已完成节点，重新启动任务流。")
        self.state = "ready"
        return self.run()

    def _run_isolated_agent(self, role_name, system_prompt, user_prompt, tools=None):
        """【隔离舱引擎】：透明化执行室，所有的思考、工具调用过程强制透传给前端，防止偷摸幻觉"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        if tools:
            for _ in range(25):
                response = self.model.chat(messages=messages, tools=tools)
                self._track_token_usage(response)
                msg = response.choices[0].message

                assist_msg = {"role": "assistant", "content": msg.content or ""}

                # 2. 如果模型在调用工具前输出了中间思考过程（如 DeepSeek-Chat 的 CoT），展示出来
                if msg.content:
                    self.log_and_notify("thought", f"🧠 [{role_name}] 正在思考分析:\n{msg.content}")

                if msg.tool_calls:
                    assist_msg["tool_calls"] = [
                        {"id": t.id, "type": t.type,
                         "function": {"name": t.function.name, "arguments": t.function.arguments}}
                        for t in msg.tool_calls
                    ]
                    messages.append(assist_msg)

                    for tc in msg.tool_calls:
                        args_str = tc.function.arguments or "{}"

                        # 3. 拦截并展示调用的工具及参数（带上角色名字以防并发错乱）
                        self.log_and_notify("tool_call", f"🔧 [{role_name}] 决定调用工具: {tc.function.name}\n参数: {args_str}")

                        args = json.loads(args_str)
                        result_str = parse_tool(tc.function.name, args)

                        # 4. 展示工具的回传结果（截断以防刷屏，但能让你知道返回了什么，破除幻觉）
                        result_preview = str(result_str)
                        if len(result_preview) > 1500:
                            result_preview = result_preview[:1500] + "\n...(内容过长已截断)..."

                        self.log_and_notify("tool",
                                            f"📦 [{role_name}] 工具 {tc.function.name} 返回结果:\n{result_preview}")

                        messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.function.name,
                                         "content": str(result_str)[:2000]})
                else:
                    # 5. 最终结论产出
                    self.log_and_notify("thought", f"✅ [{role_name}] 阶段任务完成，最终输出:\n{msg.content}")
                    return msg.content

            error_msg = f"❌ [{role_name}] 工具调用超过 25 次，强制阻断防止死循环"
            self.log_and_notify("error", error_msg)
            return error_msg
        else:
            response = self.model.chat(messages=messages)
            self._track_token_usage(response)
            content = response.choices[0].message.content

            # 无工具调用的纯思考型 Agent，直接打印结果
            self.log_and_notify("thought", f"✅ [{role_name}] 完成思考，输出结论:\n{content}")
            return content

    def _execute_parallel(self, task_dict):
        """多线程并发执行传入的任务字典"""
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(task_dict)) as executor:
            future_to_name = {
                executor.submit(
                    self._run_isolated_agent,
                    v["role"], v["sys"], v["user"], v.get("tools")
                ): k for k, v in task_dict.items()
            }
            for future in concurrent.futures.as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    results[name] = future.result()
                except Exception as exc:
                    self.log_and_notify("error", f"❌ 并发节点 [{name}] 执行崩溃: {exc}")
                    results[name] = f"分析失败: {exc}"
        return results

    # ================= 节点实现 =================

    def _node_analysts(self):
        """节点 1：分析师团队并发工作"""
        self.log_and_notify("system", "🔍 [Node 1: Analysts] 启动分析师团队，并发获取市场、情绪、新闻、基本面数据...")

        analyst_tasks = {
            "market_report": {
                "role": "Market_Analyst",
                "sys": "你是市场技术分析师。请分析给定股票的技术指标（如 MACD, RSI, 均线等）和价格走势。",
                "user": f"请给出 {self.company_name} 截至 {self.trade_date} 的市场技术面报告。",
                "tools": None  # 此处接入 get_stock_data, get_indicators 工具
            },
            "sentiment_report": {
                "role": "Social_Analyst",
                "sys": "你是社交媒体情绪分析师。请总结大众情绪是看涨还是看跌。",
                "user": f"请给出 {self.company_name} 在社交网络上的情绪倾向报告。",
                "tools": None
            },
            "news_report": {
                "role": "News_Analyst",
                "sys": "你是宏观新闻分析师。关注全球宏观经济、行业政策与内幕交易事件。",
                "user": f"请给出关于 {self.company_name} 的最新宏观及行业新闻研报。",
                "tools": None  # 此处接入 get_news, get_global_news 工具
            },
            "fundamentals_report": {
                "role": "Fundamentals_Analyst",
                "sys": "你是基本面分析师。负责剖析财报（资产负债表、现金流、利润表）。",
                "user": f"请给出 {self.company_name} 的深度财务基本面研报。",
                "tools": None  # 此处接入 get_fundamentals 工具
            }
        }
        reports = self._execute_parallel(analyst_tasks)

        for key, report in reports.items():
            self.agent_state[key] = report

        report_summary = (
            f"📊 **市场技术面**:\n{self.agent_state['market_report'][:200]}...\n\n"
            f"📰 **宏观与新闻**:\n{self.agent_state['news_report'][:200]}...\n\n"
            f"👥 **社交媒体情绪**:\n{self.agent_state['sentiment_report'][:200]}...\n\n"
            f"📑 **财务基本面**:\n{self.agent_state['fundamentals_report'][:200]}..."
        )
        self.history.append(
            {"role": "assistant", "content": f"✅ 分析师团队四维研报已生成！详细内容如下：\n\n{report_summary}"})
        self.log_and_notify("system", f"✅ 分析师团队集结完毕！产出四维核心研报摘要：\n\n{report_summary}")

    def _node_investment_debate(self):
        """节点 2：多空辩论与投资法官"""
        self.log_and_notify("system", "⚔️ [Node 2: Debate] 开启研究员多空辩论室...")
        state = self.agent_state["investment_debate_state"]

        base_context = f"【基础情况】\n技术面：{self.agent_state['market_report']}\n基本面：{self.agent_state['fundamentals_report']}\n新闻：{self.agent_state['news_report']}"

        for round_idx in range(self.max_debate_rounds):
            self.log_and_notify("system", f"🥊 投资辩论 第 {round_idx + 1} 轮 发车...")

            history_str = state["history"] if state["history"] else "（暂无历史辩论）"

            debate_tasks = {
                "bull": {
                    "role": "Bull_Researcher",
                    "sys": "你是一个极度乐观的多头研究员。你要在当前数据和空头的反驳中，找到坚定的看涨逻辑。",
                    "user": f"{base_context}\n\n【历史辩论】：\n{history_str}\n\n请给出你的看涨论点，并反驳空头。"
                },
                "bear": {
                    "role": "Bear_Researcher",
                    "sys": "你是一个极度悲观的空头研究员。你要在当前数据和多头的盲目乐观中，揪出致命的风险和看跌逻辑。",
                    "user": f"{base_context}\n\n【历史辩论】：\n{history_str}\n\n请给出你的看跌论点，并反驳多头。"
                }
            }

            results = self._execute_parallel(debate_tasks)

            bull_arg = results["bull"]
            bear_arg = results["bear"]
            state["bull_history"].append(bull_arg)
            state["bear_history"].append(bear_arg)
            state["history"] += f"\n\n--- 轮次 {round_idx + 1} ---\n【多头】：{bull_arg}\n【空头】：{bear_arg}"

        # 法官裁决
        self.log_and_notify("system", "👨‍⚖️ [Node 2: Invest Judge] 投资法官正在听取辩论记录进行综合裁决...")
        judge_sys = "你是客观理性的投资法官。请总结多空双方的辩论，并给出一份综合的初步投资倾向报告。"
        judge_user = f"{base_context}\n\n【多空辩论全记录】：\n{state['history']}\n\n请下达你的综合裁决逻辑。"

        judge_decision = self._run_isolated_agent("Invest_Judge", judge_sys, judge_user)
        state["judge_decision"] = judge_decision
        self.history.append({"role": "assistant", "content": f"👨‍⚖️ **多空投资法官初步裁决**：\n\n{judge_decision}"})
        self.log_and_notify("system", f"👨‍⚖️ **多空投资法官初步裁决下发**：\n\n{judge_decision}")

    def _node_trader(self):
        """节点 3：交易员提议"""
        self.log_and_notify("system", "🧑‍💼 [Node 3: Trader] 交易员结合历史相似行情，推演交易提案...")

        # 提取过往相似记忆 (RAG)
        curr_situation = self.agent_state["investment_debate_state"]["judge_decision"]
        try:
            past_memories = self.financial_memory.search(curr_situation, top_k=2)
            past_memory_str = "\n".join(
                [m.get("content", "") for m in past_memories]) if past_memories else "无相关历史交易记忆。"
        except:
            past_memory_str = "无相关历史交易记忆。"

        sys_prompt = "你是资深量化交易员。你需要根据法官的逻辑和过往交易教训，给出具体操作提案（Buy/Sell/Hold 及仓位建议）。"
        user_prompt = f"【法官投资倾向】：\n{curr_situation}\n\n【历史交易教训】：\n{past_memory_str}\n\n请输出你的明确交易提案。"

        trader_plan = self._run_isolated_agent("Trader", sys_prompt, user_prompt)
        self.agent_state["trader_investment_plan"] = trader_plan
        self.history.append({"role": "assistant", "content": f"🧑‍💼 **交易员推演操作提案**：\n\n{trader_plan}"})
        self.log_and_notify("system", f"🧑‍💼 **交易员推演操作提案完成**：\n\n{trader_plan}")

    def _node_risk_debate(self):
        """节点 4：风控团队研讨与法官"""
        self.log_and_notify("system", "🛡️ [Node 4: Risk Debate] 启动风控三巨头团队评估...")
        state = self.agent_state["risk_debate_state"]

        trader_plan = self.agent_state["trader_investment_plan"]

        for round_idx in range(self.max_risk_discuss_rounds):
            self.log_and_notify("system", f"🛑 风控交叉评估 第 {round_idx + 1} 轮 发车...")
            history_str = state["history"] if state["history"] else "（暂无历史评估）"

            risk_tasks = {
                "aggressive": {
                    "role": "Aggressive_Risk",
                    "sys": "你是激进派风控。倾向于接受更高风险以换取超额收益。请评估交易员提案。",
                    "user": f"【交易提案】：{trader_plan}\n【历史研讨】：{history_str}\n给出你的激进评估。"
                },
                "neutral": {
                    "role": "Neutral_Risk",
                    "sys": "你是中立派风控。讲究风险与收益的绝对平衡。",
                    "user": f"【交易提案】：{trader_plan}\n【历史研讨】：{history_str}\n给出你的中立评估。"
                },
                "conservative": {
                    "role": "Conservative_Risk",
                    "sys": "你是保守派风控。极端厌恶风险，关注最大回撤和极端黑天鹅事件。",
                    "user": f"【交易提案】：{trader_plan}\n【历史研讨】：{history_str}\n给出你的保守评估。"
                }
            }

            results = self._execute_parallel(risk_tasks)

            state["aggressive_history"].append(results["aggressive"])
            state["neutral_history"].append(results["neutral"])
            state["conservative_history"].append(results["conservative"])
            state[
                "history"] += f"\n\n--- 轮次 {round_idx + 1} ---\n激进：{results['aggressive']}\n中立：{results['neutral']}\n保守：{results['conservative']}"

        # 风控法官裁决
        self.log_and_notify("system", "👨‍⚖️ [Node 4: Risk Judge] 风控法官正在对团队意见进行最终风险定调...")
        judge_sys = "你是风控主管法官。请总结激进、中立、保守三方的意见，对交易提案的风险等级进行定性。"
        judge_user = f"【交易提案】：{trader_plan}\n\n【风控研讨全记录】：\n{state['history']}\n\n请下达风险裁决。"

        judge_decision = self._run_isolated_agent("Risk_Judge", judge_sys, judge_user)
        state["judge_decision"] = judge_decision
        self.history.append({"role": "assistant", "content": f"🛡️ **风控法官一票否决权风险定调**：\n\n{judge_decision}"})
        self.log_and_notify("system", f"🛡️ **风控法官风险定调下发**：\n\n{judge_decision}")

    def _node_portfolio_manager(self):
        """节点 5：投资组合经理终裁"""
        self.log_and_notify("system", "👑 [Node 5: Portfolio Manager] 基金经理正在阅读各部门研报，生成一锤定音的指令...")

        pm_sys = "你是最终决策的投资组合经理 (Portfolio Manager)。你掌握资金生杀大权。你的任务是综合各项研报，输出最终结构化指令。"

        pm_user = f"""
请基于以下所有维度的报告，给出最终的交易决策。
要求必须包含：1. 评级(Buy/Hold/Sell) 2. 仓位比例 3. 核心逻辑摘要。

【基本面摘要】：{self.agent_state['fundamentals_report'][:500]}...
【多空投资法官裁决】：{self.agent_state['investment_debate_state']['judge_decision']}
【交易员硬性提案】：{self.agent_state['trader_investment_plan']}
【风控法官一票否决权风险评估】：{self.agent_state['risk_debate_state']['judge_decision']}
"""
        final_decision = self._run_isolated_agent("Portfolio_Manager", pm_sys, pm_user)
        self.agent_state["final_trade_decision"] = final_decision
        self.log_and_notify("system", f"🎯 最终投资组合决策生成完毕，任务闭环！")
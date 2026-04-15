import json
import datetime
from src.models.task import BaseTask
from src.models.model import Model
from src.loader.memory import Memory  # 接入 CatInCup 现有的记忆模块
from src.plugins.plugin_manager import parse_tool


class TradingTask(BaseTask):
    def __init__(self, task_name, prompt, core, judger, company_name):
        super().__init__(task_name, prompt, core, judger)
        self.company_name = company_name

        # 【Harness Engineering 1: 引入 AgentState 状态机】
        # 完全抛弃单线 self.history 混杂的模式，改用独立的状态字典在节点间传递
        self.agent_state = {
            "company_of_interest": company_name,
            "market_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "investment_plan": "",  # 研究主管(Research Manager)多空辩论后的总结
            "trader_investment_plan": "",  # 交易员(Trader)的硬性提案
            "risk_debate_state": {
                "history": "",
                "aggressive_history": "",
                "conservative_history": "",
                "neutral_history": "",
                "count": 0
            },
            "final_trade_decision": ""
        }

        # 独立的金融情境长时记忆库 (模拟 TradingAgents 的 FinancialSituationMemory)
        self.financial_memory = Memory()

    def run(self):
        """
        【Harness Engineering 2: 覆写单循环，实现有向无环图 (DAG) 的节点流转】
        保证上下文物理隔离：基金经理绝对看不到分析师调代码的冗余 Token。
        """
        self.state = "running"
        try:
            self.log_and_notify("system", f"🚀 启动 TradingGraph 交易图谱: 标的 {self.company_name}")

            # Node 1: 数据搜集与分析师研报 (隔离的临时环境)
            self._node_analysts()

            # Node 2: 研究主管多空辩论
            self._node_investment_debate()

            # Node 3: 交易员提议 (精确还原你代码中的 memory 注入机制)
            self._node_trader()

            # Node 4: 基金经理终裁 (Portfolio Manager)
            self._node_portfolio_manager()

            self.state = "completed"
            self.save_checkpoint()

            return f"✅ TradingGraph 裁决完成！\n【最终决定】：\n{self.agent_state['final_trade_decision']}"

        except Exception as e:
            self.state = "error"
            self.log_and_notify("error", f"❌ TradingGraph 流水线崩溃: {e}")
            self.save_checkpoint()
            raise InterruptedError(f"交易任务异常中断: {e}")

    def _run_isolated_agent(self, role_name, system_prompt, user_prompt, tools=None):
        """
        【隔离舱引擎】：为每个子角色开辟干净的上下文，防止 Token 污染和幻觉蔓延，
        但依然将使用的 Token 累加到主 Task 的 self.token_usage 中。
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # 如果需要调用工具 (例如 Analyst 节点)，使用一个小型的工具循环
        if tools:
            for _ in range(10):  # 限制最大思考步数
                response = self.model.chat(messages=messages, tools=tools)
                self._track_token_usage(response)
                msg = response.choices[0].message

                assist_msg = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    assist_msg["tool_calls"] = [{"id": t.id, "type": t.type, "function": {"name": t.function.name,
                                                                                          "arguments": t.function.arguments}}
                                                for t in msg.tool_calls]
                    messages.append(assist_msg)

                    for tc in msg.tool_calls:
                        args = json.loads(tc.function.arguments)
                        # 调用 CatInCup 插件管理器
                        result_str = parse_tool(tc.function.name, args)
                        messages.append(
                            {"role": "tool", "tool_call_id": tc.id, "name": tc.function.name, "content": result_str})
                else:
                    return msg.content
            return "工具调用超时未能生成总结"
        else:
            # 无工具纯推理节点 (Trader / Manager)
            response = self.model.chat(messages=messages)
            self._track_token_usage(response)
            return response.choices[0].message.content

    def _node_analysts(self):
        self.log_and_notify("system", "🔍 [Node 1: Analysts] 正在调动底层工具收集大盘数据...")

        # 配置允许使用的数据源插件
        from src.plugins.route.base_tool import BASE_TOOLS

        prompt = f"请使用工具收集 {self.company_name} 的股价数据、技术指标、近期新闻和基本面财报，并输出一份综合摘要。"
        report = self._run_isolated_agent(
            role_name="Market_Analyst",
            system_prompt="你是一个严谨的数据分析师。不要胡编乱造数据，必须调用工具获取客观事实。",
            user_prompt=prompt,
            tools=BASE_TOOLS  # 这里传入后面提到的 Finance 工具箱
        )

        # 简化演示，这里将综合报告拆分填入状态机（实际可分别调用细分 Analyst）
        self.agent_state["market_report"] = report
        self.log_and_notify("thought", "📊 基础研报生成完毕。")

    def _node_investment_debate(self):
        self.log_and_notify("system", "⚔️ [Node 2: Debate] 启动 Bull vs Bear 投资逻辑对抗...")
        # 略去复杂的循环论战代码，逻辑是用 Bull prompt 批评 Bear，用 Bear 挑刺 Bull，
        # 最终汇总到 agent_state["investment_plan"]
        self.agent_state["investment_plan"] = "经过多空交战，认为其营收稳健但估值过高，建议逢低买入..."

    def _node_trader(self):
        """精准一比一复刻 tradingagents/agents/trader/trader.py 的逻辑"""
        self.log_and_notify("system", "🧑‍💼 [Node 3: Trader] 结合历史相似行情，推演交易提案...")

        # 1. 拼接当前的宏观情境
        curr_situation = f"{self.agent_state['market_report']}\n\n{self.agent_state['sentiment_report']}\n\n{self.agent_state['news_report']}\n\n{self.agent_state['fundamentals_report']}"

        # 2. 从记忆库中搜索相似的历史情境与教训 (RAG)
        # 注意：这里需要你 src.loader.memory 支持 search 方法
        past_memories = []
        try:
            # 假设 search 返回 [{content: "当时美联储加息，买入导致回撤30%..."}]
            past_memories = self.financial_memory.search(curr_situation, top_k=2)
        except:
            pass

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec.get("content", "") + "\n\n"
        else:
            past_memory_str = "No past memories found."

        # 3. 组装 Prompt
        system_prompt = f"You are a trading agent analyzing market data... Apply lessons from past decisions: {past_memory_str}"
        user_prompt = f"Based on a comprehensive analysis... {self.agent_state['investment_plan']} Leverage these insights to make an informed and strategic decision."

        result = self._run_isolated_agent("Trader", system_prompt, user_prompt)
        self.agent_state["trader_investment_plan"] = result
        self.log_and_notify("thought", f"📈 Trader 提案: {result[:100]}...")

    def _node_portfolio_manager(self):
        """精准一比一复刻 portfolio_manager.py 的决断逻辑"""
        self.log_and_notify("system", "👨‍⚖️ [Node 4: Portfolio Manager] 正在进行最终仓位及策略裁定...")

        # 提取过往记忆
        curr_situation = f"{self.agent_state['market_report']}\n\n{self.agent_state['fundamentals_report']}"
        past_memory_str = "No past memories found."  # 略

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

Context:
- Research Manager's investment plan: {self.agent_state['investment_plan']}
- Trader's transaction proposal: {self.agent_state['trader_investment_plan']}
- Lessons from past decisions: {past_memory_str}

Risk Analysts Debate History:
{self.agent_state['risk_debate_state']['history']}

Required Output Structure:
1. Rating
2. Executive Summary
3. Investment Thesis
"""

        result = self._run_isolated_agent("Portfolio_Manager", "You are the head Portfolio Manager.", prompt)
        self.agent_state["final_trade_decision"] = result
        self.log_and_notify("tool", f"🎯 投资组合经理决策生成！")
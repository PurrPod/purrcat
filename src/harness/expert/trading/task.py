"""
Trading Expert: 专业量化交易专家

架构: 3-Phase Pipeline
  Phase 1: 并行采集数据 (3路)
  Phase 2: 综合研判 + 交易计划 (1次模型调用)
  Phase 3: 风控终裁 (1次模型调用)

相比旧版(7节点/16次调用): 3阶段/5次调用, -69%模型开销
"""
import json
import concurrent.futures
from src.harness.task import BaseTask

from src.harness.expert.trading.extend_tool import (
    EXTEND_TOOL_FUNCTIONS, EXTEND_TOOLS_SCHEMA, handle_extend_tool,
)
from src.harness.expert.trading.extend_tool.kv_cache import get_cache
from src.harness.expert.trading.extend_tool.data_sources import (
    get_stock_data, get_market_info, search_market_news,
)


class TradingTask(
    BaseTask,
    expert_type="trading",
    description="量化交易专家，负责股票的多空辩论、基本面/技术面分析及风险定调。",
    parameters={
        "company_name": {
            "type": "string",
            "description": "要分析的公司名称或股票代码（如 '600519', 'AAPL'）",
            "required": True
        },
        "trade_date": {
            "type": "string",
            "description": "交易分析的基准日期",
            "required": False,
            "default": "Current"
        }
    }
):
    def __init__(self, task_name, prompt, core, company_name, trade_date=None):
        super().__init__(task_name, prompt, core)
        self.company_name = company_name
        self.trade_date = trade_date or "Current"
        self._data = {}
        self._kv = get_cache()
        self.analysis_result = ""
        self.final_decision = ""
        self.log_and_notify("system", f"📊 交易专家启动: {company_name} @ {trade_date}")

    def get_available_tools(self):
        tools = super().get_available_tools() or []
        tools.extend(EXTEND_TOOLS_SCHEMA)
        return tools

    # ============ Phase 1: 并行数据采集 ============
    def _phase_data(self):
        self.log_and_notify("system", f"📡 [1/3] 数据采集: {self.company_name}")
        code = self.company_name
        
        def t1():
            return f"【行情+技术】\n{get_stock_data(code, 'tech')}"
        def t2():
            return f"【市场情绪】\n{get_market_info('all')}"
        def t3():
            return f"【新闻】\n{search_market_news(f'{code} 股票 研报', 6)}"

        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            futs = {pool.submit(t1): "tech", pool.submit(t2): "sentiment", pool.submit(t3): "news"}
            for f in concurrent.futures.as_completed(futs):
                self._data[futs[f]] = f.result(timeout=30)

        sz = sum(len(v) for v in self._data.values())
        self.log_and_notify("system", f"✅ 数据采集完成: {sz}字")

    # ============ Phase 2: 综合研判 ============
    def _phase_analysis(self):
        self.log_and_notify("system", f"🧠 [2/3] 综合分析: {self.company_name}")
        
        report = "\n\n".join(self._data.get(k,"") for k in ["tech","sentiment","news"])
        
        # KV cache check
        if self._kv.get("analysis", [{"role":"user","content":self.company_name}], "v2"):
            self.analysis_result = self._kv.get("analysis", [{"role":"user","content":self.company_name}], "v2")
            self.log_and_notify("system", "⚡ KV 命中")
            self.history.append({"role":"assistant","content":self.analysis_result})
            return

        sys = f"""你是一名资深买方研究员，当前日期：{self.trade_date}。
基于以下数据对 {self.company_name} 进行深度分析，输出结构化报告：

1. **行情定位**：价格位置、均线排列、布林带位置
2. **技术面**：MACD状态、RSI(超买/超卖)、KDJ、ADX趋势强度、成交量验证
3. **多空辩论**：看多逻辑(≥2条) vs 看空逻辑(≥2条)
4. **交易计划**：方向(买入/持有/卖出/观望)、仓位(轻/半/重)、关键价位(支撑/压力/止损)

格式清晰，数据说话，不废话。"""

        result = self._run_model(sys, f"数据报告：\n\n{report}")
        self.analysis_result = result
        self._kv.set("analysis", [{"role":"user","content":self.company_name}], result, "v2")
        self.history.append({"role":"assistant","content":f"## 📊 分析报告\n\n{result}"})

    # ============ Phase 3: 风控终裁 ============
    def _phase_risk(self):
        self.log_and_notify("system", f"🛡️ [3/3] 风控终裁: {self.company_name}")

        if self._kv.get("risk", [{"role":"user","content":self.company_name}], "v2"):
            self.final_decision = self._kv.get("risk", [{"role":"user","content":self.company_name}], "v2")
            self.log_and_notify("system", "⚡ KV 命中(风控)")
            self.history.append({"role":"assistant","content":self.final_decision})
            return

        sys = f"""你是一名投资组合经理。基于分析报告做风控定调和最终决策。
当前日期：{self.trade_date}

评估维度：
- 风险评估：最大回撤、黑天鹅、流动性
- 情景分析：乐观(+10%)/基准(0%)/悲观(-10%) 概率与应对
- 最终决策：评级(强力买入/买入/持有/减仓/卖出)、仓位%、核心逻辑"""

        result = self._run_model(sys, f"分析报告：\n\n{self.analysis_result}")
        self.final_decision = result
        self._kv.set("risk", [{"role":"user","content":self.company_name}], result, "v2")
        self.history.append({"role":"assistant","content":f"## 🎯 最终决策\n\n{result}"})

    # ============ 执行 ============
    def run(self):
        try:
            self._phase_data()
            self._phase_analysis()
            self._phase_risk()
            self._kv.persist()
            
            summary = (
                f"## 📋 {self.company_name} 交易分析报告\n\n"
                f"**日期**: {self.trade_date}\n\n"
                f"**数据**: 腾讯行情 + 技术指标 + 北向资金 + 百度热搜\n\n"
                f"**结论**:\n{self.final_decision[:800]}"
            )
            self.history.append({"role":"assistant","content":summary})
            self.log_and_notify("system", summary)
            self._call_done()
        except Exception as e:
            self.log_and_notify("system", f"❌ 异常: {e}")
            import traceback; traceback.print_exc()
            self.state = "error"
            raise

    def _run_model(self, sys_prompt: str, user_msg: str) -> str:
        try:
            resp = self.model.chat(messages=[
                {"role":"system","content":sys_prompt},
                {"role":"user","content":user_msg}
            ], temperature=0.3)
            return resp.content if hasattr(resp,'content') else str(resp)
        except Exception as e:
            return f"[模型调用异常: {e}]"

    def _call_done(self):
        try:
            from src.agent.tool_func import task_done
            task_done(self.task_id, "交易分析完成")
        except: pass
        self.state = "completed"

    def _on_save_state(self) -> dict:
        return {"analysis": self.analysis_result, "decision": self.final_decision}

    def _on_restore_state(self, state: dict):
        e = state.get("extra_state", {})
        self.analysis_result = e.get("analysis","")
        self.final_decision = e.get("decision","")

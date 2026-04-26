"""

Trading Expert 三阶段流水线

Phase 1 — 数据采集 (1轮模型调用)
Phase 2 — 技术面+基本面分析 (1轮模型调用)
Phase 3 — 多空辩论 (1轮模型调用, 同时生成多空双方观点)

合计: 3轮大模型调用 (优化后, 原16轮)

架构要点:
  - 固定长 system prompt → 利用大模型厂商侧 Prefix KV Cache 节省推理费用
  - 每阶段只用 1 次粗粒度调用, 避免回合对话
  - 所有数据在 Phase 1 集齐, Phase 2/3 直接使用
"""
import json
import time
import traceback
from typing import Any, Optional

from .extend_tool import handle_extend_tool, get_extend_tools_schema

TOOLS = get_extend_tools_schema()

# ---------------------------------------------------------------------------
# Phase 1 — 数据采集
# ---------------------------------------------------------------------------

PHASE1_SYSTEM_PROMPT = """你是一个量化交易数据采集代理。你的工作分为两步：
第一步，调用 get_stock_data 获取全部数据（code参数传公司代号，mode传all），获取基本面行情和技术全量数据。
第二步，使用 get_market_info 获取市场整体情况。
请注意，如果在第一步的工具调用中出错或者获取的数据里因为节假日、非交易日导致某些数据缺失
（比如ADR、技术指标、北向资金等字段为空或0），这些都属于正常现象，直接告知用户缺失即可，不必重试。
你只需获取数据后如实整理输出即可，不要做分析。"""

# ---------------------------------------------------------------------------
# Phase 2 — 分析
# ---------------------------------------------------------------------------

PHASE2_SYSTEM_PROMPT = """你是资深量化分析师，擅长技术分析与基本面分析相结合。请根据提供的完整数据，进行深入且结构化的分析。

你的分析必须涵盖但不限于以下维度：

一、技术面分析
  - 趋势维度：MA均线排列（多头/空头排列，短期/长期交叉信号）、ADX趋势强度（强趋势/弱震荡，方向判断）
  - 动量维度：MACD柱状图变化（金叉/死叉信号，动能增强/减弱）、RSI超买超卖区间（是否有背离信号）、WR威廉指标位置（趋势确认）
  - 波动维度：布林带位置（价格处于上/中/下轨，开口/收口预示趋势或震荡）、ATR波动率变化（是否异常放大预示变盘）
  - 成交量维度：OBV与价格关系（量价配合/背离）

二、基本面分析
  - 估值维度：当前市盈率（PE）在行业和历史分位水平，市值规模
  - 市场定位：该标的基本面特征总结

三、综合分析
  - 多周期共振/矛盾：分析日线级别的技术信号是否存在矛盾，给出综合判断
  - 关键支撑压力位：根据布林带和均线给出明确的价位区间
  - 风险提示：当前最值得关注的潜在风险（技术面/基本面均可）

请保持专业客观，注重具体价位和信号而非模糊描述。
注意：如果某些技术指标因节假日、非交易日或其他原因缺失（字段为0或空），说明该指标无法计算，不要强行解读。
"""

# ---------------------------------------------------------------------------
# Phase 3 — 多空辩论
# ---------------------------------------------------------------------------

BULL_PROMPT = """你是乐观但有理有据的多头分析师。请基于提供的数据和分析结果，从看多角度出发进行论述。

请按以下结构展开：
1. 核心看多逻辑（列出2-3个最有力的看多理由，必须有数据支撑）
2. 技术面看多信号（指出具体的技术指标和价位，给出明确的做多/建仓参考位置）
3. 基本面支撑（估值合理/成长性好等，如果有数据支撑）
4. 目标价位（给出合理的目标价区间及依据）
5. 风险控制提示（承认潜在风险，给出止损位建议）

要求：给出具体价位建议，乐观但不能盲目。"""

BEAR_PROMPT = """你是谨慎但有理有据的空头分析师。请基于提供的数据和分析结果，从看空角度出发进行论述。

请按以下结构展开：
1. 核心看空逻辑（列出2-3个最有力的看空理由，必须有数据支撑）
2. 技术面看空信号（指出具体的技术指标和价位，给出明确的做空/离场参考位置）
3. 基本面隐忧（估值过高/增长乏力等，如果有数据支撑）
4. 下行目标价位（给出合理的下行目标区间及依据）
5. 风险控制提示（承认看错的风险，给出止损位建议）

要求：给出具体价位建议，谨慎但不能刻意唱空。"""

# ---------------------------------------------------------------------------
# 工具调用辅助
# ---------------------------------------------------------------------------

def _call_tools(llm, msg, tools=None):
    """调用 LLM 并处理可能的工具调用"""
    if tools is not None:
        response = llm.call(messages=msg, tools=tools, tool_choice="auto")
        tool_calls = response.get("tool_calls", [])
        if not tool_calls and isinstance(response, dict) and "content" in response:
            return response.get("content", "")
        if not tool_calls:
            tool_calls = response.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {}) if isinstance(tc, dict) else tc.function
                name = func.get("name", "")
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except:
                    args = {}
                ok, result = handle_extend_tool(name, args, None)
                msg.append({"role": "tool", "tool_call_id": tc.get("id",""), "content": result})
            second_response = llm.call(messages=msg, tools=tools)
            if isinstance(second_response, dict):
                return second_response.get("content", str(second_response))
            return str(second_response)
        return response
    else:
        response = llm.call(messages=msg)
        if isinstance(response, dict):
            return response.get("content", str(response))
        return str(response)


def _simple_call(llm, msg, system_prompt):
    """纯文本调用，无工具"""
    msgs = [{"role": "system", "content": system_prompt}, {"role": "user", "content": msg}]
    response = llm.call(messages=msgs)
    if isinstance(response, dict):
        return response.get("content", str(response))
    return str(response)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def run_task(llm, task: Any, params: dict) -> str:
    company = params.get("company", "")
    date = params.get("trade_date", "")
    analyze_type = params.get("analyze_type", "deep")
    if not company:
        return "请指定公司"

    start = time.time()
    result = {"company": company, "date": date, "phases": {}}

    try:
        # ============ Phase 1: 数据采集 ============
        phase1_start = time.time()
        phase1_msgs = [{"role": "system", "content": PHASE1_SYSTEM_PROMPT},
                       {"role": "user", "content": f"请获取 {company} 的完整股票数据和市场整体情况。日期: {date}"}]
        phase1_result = _call_tools(llm, phase1_msgs, TOOLS)
        result["phases"]["data_collection"] = {
            "output": phase1_result,
            "time": round(time.time() - phase1_start, 2)
        }

        # ============ Phase 2: 分析 ============
        phase2_start = time.time()
        phase2_result = _simple_call(
            llm,
            f"请对 {company} 进行技术面和基本面分析。\n\n完整数据如下：\n{phase1_result}",
            PHASE2_SYSTEM_PROMPT
        )
        result["phases"]["analysis"] = {
            "output": phase2_result,
            "time": round(time.time() - phase2_start, 2)
        }

        # ============ Phase 3: 多空辩论 ============
        if analyze_type == "deep":
            phase3_start = time.time()
            combined_msg = (
                f"基于以下对 {company} 的分析结果：\n\n"
                f"[Phase 1 数据]\n{phase1_result}\n\n"
                f"[Phase 2 分析]\n{phase2_result}\n\n"
                f"请从多空双方分别进行深入论述。"
            )

            # 多头论述
            bull_result = _simple_call(llm, combined_msg, BULL_PROMPT)
            # 空头论述
            bear_result = _simple_call(llm, combined_msg, BEAR_PROMPT)

            result["phases"]["bull"] = {"output": bull_result, "time": round(time.time() - phase3_start, 2)}
            result["phases"]["bear"] = {"output": bear_result, "time": round(time.time() - phase3_start, 2)}

    except Exception as e:
        return json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False)

    total_time = round(time.time() - start, 2)
    result["total_time"] = total_time

    # ============ 组装最终输出 ============
    lines = []
    lines.append(f"## {company} 交易分析报告 ({date})")
    lines.append(f"*分析耗时: {total_time}s*\n")
    lines.append(f"### 📊 数据采集")
    lines.append(result["phases"].get("data_collection", {}).get("output", ""))
    lines.append(f"\n### 🔬 技术面 & 基本面分析")
    lines.append(result["phases"].get("analysis", {}).get("output", ""))
    if analyze_type == "deep":
        lines.append(f"\n### 🐂 多头观点")
        lines.append(result["phases"].get("bull", {}).get("output", ""))
        lines.append(f"\n### 🐻 空头观点")
        lines.append(result["phases"].get("bear", {}).get("output", ""))

    return "\n".join(lines)
"""
Trading Expert: 专业金融数据源工具集

架构:
  Circuit Breaker (熔断) → Retry (重试) → Fallback (降级)
  
数据源:
  - A股实时行情: 腾讯 HTTP API (高可用)
  - A股 K线: 腾讯 HTTP API (降级备用)
  - A股 K线+财务: AKShare (主用, 需HTTPS)
  - 市场情绪: 百度热搜 + 大盘腾讯指数
  - 新闻搜索: DDGS (DuckDuckGo)
  
容错设计:
  1. Circuit Breaker: 连续3次失败熔断60s
  2. Retry: 指数退避 (0.5s → 1s)
  3. Fallback: HTTPS失败 → HTTP降级 → 返回基础信息
"""
import json
import logging
import threading
import time
import requests
import pandas as pd

logger = logging.getLogger(__name__)

# ============================
# 熔断器
# ============================
class CircuitBreaker:
    def __init__(self, name: str, threshold: int = 3, cooldown: int = 60):
        self.name = name
        self.threshold = threshold
        self.cooldown = cooldown
        self._fc = 0
        self._last = 0
        self._state = "closed"
        self._lock = threading.Lock()

    def call(self, func, *args, **kwargs):
        with self._lock:
            if self._state == "open":
                if time.time() - self._last > self.cooldown:
                    self._state = "half-open"
                else:
                    raise Exception(f"[CB:{self.name}] OPEN")
        try:
            r = func(*args, **kwargs)
            with self._lock:
                self._fc = 0; self._state = "closed"
            return r
        except Exception as e:
            with self._lock:
                self._fc += 1; self._last = time.time()
                if self._fc >= self.threshold:
                    self._state = "open"
            raise e

_CBS = {}
def _cb(name): 
    if name not in _CBS: _CBS[name] = CircuitBreaker(name)
    return _CBS[name]

def _retry(n=2, d=0.5):
    def dec(f):
        def wrapper(*a, **kw):
            last = None; delay = d
            for i in range(n):
                try: return f(*a, **kw)
                except Exception as e:
                    last = e
                    if i < n-1: time.sleep(delay); delay *= 2
            raise last
        return wrapper
    return dec

# ============================
# 代码工具
# ============================
def _normalize(code: str) -> tuple:
    code = code.strip().upper()
    if code.isalpha(): return ("us", code, code)
    if code.startswith("SH"): return ("cn", code.lower(), code[2:])
    if code.startswith("SZ"): return ("cn", code.lower(), code[2:])
    if code.isdigit():
        p = "sh" if code[0] in ("6","9") else "sz"
        return ("cn", p+code, code)
    return ("unknown", code, code)

# ============================
# 数据源 1: 腾讯行情 (HTTP, 最可靠)
# ============================
@_retry(n=2, d=0.5)
def _tencent_price(code: str) -> dict:
    r = requests.get(f"http://qt.gtimg.cn/q={code}", timeout=5)
    if r.status_code != 200: raise Exception(f"HTTP {r.status_code}")
    f = r.text.split("=")[1].strip('\";\n').split("~")
    if len(f) < 45: raise Exception(f"fields={len(f)}")
    return {
        "name": f[1], "code": f[2],
        "price": float(f[3] or 0), "change_pct": float(f[32] or 0),
        "change_amt": float(f[31] or 0),
        "high": float(f[33] or 0), "low": float(f[34] or 0),
        "open": float(f[5] or 0), "pre_close": float(f[4] or 0),
        "volume": int(f[6] or 0), "amount_wan": float(f[37] or 0),
        "turnover_rate": float(f[38] or 0),
        "pe_ttm": float(f[39] or 0),
        "market_cap_yi": float(f[45] or 0),
        "amplitude": float(f[43] or 0),
        "source": "tencent",
    }

# ============================
# 数据源 2: 腾讯 K线 (HTTP)
# ============================
@_retry(n=2, d=0.5)
def _tencent_kline(code: str, days: int = 120) -> list:
    """获取腾讯K线数据, 返回 [date, open, close, high, low, volume]"""
    r = requests.get(f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{days},qfq", timeout=10)
    if r.status_code != 200: raise Exception(f"HTTP {r.status_code}")
    d = r.json()
    data = d.get("data", {}).get(code, {})
    kline = data.get("qfqday") or data.get("day") or []
    if not kline: raise Exception("empty kline")
    return kline  # [[date, open, close, high, low, volume], ...]

# ============================
# 数据源 3: AKShare (HTTPS, 主用)
# ============================
def _akshare_kline(code: str, days: int = 120) -> list:
    try:
        import akshare as ak
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        if df is None or df.empty: return None
        df = df.tail(days)
        return [[row["日期"].strftime("%Y-%m-%d"),
                 float(row["开盘"]), float(row["收盘"]),
                 float(row["最高"]), float(row["最低"]),
                 int(row["成交量"])] for _, row in df.iterrows()]
    except Exception as e:
        logger.warning(f"akshare kline failed: {e}")
        return None

# ============================
# 技术指标计算 (pandas)
# ============================
def _calc_indicators(closes, highs, lows, volumes):
    c = pd.Series(closes); h = pd.Series(highs); l_ = pd.Series(lows); v = pd.Series(volumes)
    r = {}
    for p in [5,10,20,60]: r[f"MA{p}"] = round(float(c.rolling(p).mean().iloc[-1]), 2)
    e12 = c.ewm(span=12,adjust=False).mean(); e26 = c.ewm(span=26,adjust=False).mean()
    dif = e12-e26; dea = dif.ewm(span=9,adjust=False).mean()
    r["MACD"] = {"DIF": round(float(dif.iloc[-1]),3), "DEA": round(float(dea.iloc[-1]),3),
                 "HIST": round(float((dif-dea).iloc[-1]),3)}
    delta = c.diff()
    gain = delta.where(delta>0,0).rolling(14).mean()
    loss = (-delta.where(delta<0,0)).rolling(14).mean()
    rs = gain / loss.replace(0,float('inf'))
    r["RSI"] = round(float((100-(100/(1+rs))).iloc[-1]), 2)
    mid = c.rolling(20).mean(); std = c.rolling(20).std()
    r["Bollinger"] = {"UPPER": round(float((mid+2*std).iloc[-1]),2),
                      "MID": round(float(mid.iloc[-1]),2),
                      "LOWER": round(float((mid-2*std).iloc[-1]),2)}
    low14 = l_.rolling(14).min(); high14 = h.rolling(14).max()
    rsv = (c-low14)/(high14-low14).replace(0,float('inf'))*100
    k_ = rsv.ewm(com=2,adjust=False).mean()
    d_ = k_.ewm(com=2,adjust=False).mean()
    r["KDJ"] = {"K": round(float(k_.iloc[-1]),2), "D": round(float(d_.iloc[-1]),2),
                "J": round(float((3*k_-2*d_).iloc[-1]),2)}
    r["Volume"] = {"latest": int(v.iloc[-1]),
                   "MA5": int(round(v.rolling(5).mean().iloc[-1])),
                   "MA20": int(round(v.rolling(20).mean().iloc[-1]))}
    # ADX
    tr = pd.concat([h-l_, abs(h-c.shift(1)), abs(l_-c.shift(1))], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    up = h-h.shift(1); down = l_.shift(1)-l_
    plus_dm = ((up>down)&(up>0)).astype(float)*up
    minus_dm = ((down>up)&(down>0)).astype(float)*down
    plus_di = 100*(plus_dm.ewm(span=14).mean()/atr14)
    minus_di = 100*(minus_dm.ewm(span=14).mean()/atr14)
    dx = 100*abs(plus_di-minus_di)/(plus_di+minus_di).replace(0,float('inf'))
    r["ADX"] = round(float(dx.ewm(span=14).mean().iloc[-1]), 2)
    r["ATR"] = round(float(atr14.iloc[-1]), 2)
    # OBV
    obv = (v * ((c.diff()>0).astype(int)*2-1)).cumsum()
    r["OBV"] = int(obv.iloc[-1])
    # W%R
    hh14 = h.rolling(14).max(); ll14 = l_.rolling(14).min()
    r["WR"] = round(float(((hh14-c)/(hh14-ll14).replace(0,float('inf'))*-100).iloc[-1]), 2)
    return r

def _fmt_tech(code, price, indicators):
    pos5 = "↑上方" if price > indicators["MA5"] else "↓下方"
    pos20 = "↑上方" if price > indicators["MA20"] else "↓下方"
    rsi_s = "超买" if indicators["RSI"]>70 else ("超卖" if indicators["RSI"]<30 else "中性")
    bbw = (indicators["Bollinger"]["UPPER"]-indicators["Bollinger"]["LOWER"])/max(indicators["Bollinger"]["MID"],0.01)*100
    return (
        f"【{code} 技术分析】\n"
        f"收盘: {price}\n\n"
        f"--- 均线 ---\n"
        f"MA5: {indicators['MA5']} ({pos5})  MA10: {indicators.get('MA10','')}\n"
        f"MA20: {indicators['MA20']} ({pos20})  MA60: {indicators['MA60']}\n\n"
        f"--- MACD ---\n"
        f"DIF: {indicators['MACD']['DIF']}  DEA: {indicators['MACD']['DEA']}  "
        f"柱: {indicators['MACD']['HIST']} ({'多头' if indicators['MACD']['HIST']>0 else '空头'})\n\n"
        f"--- RSI(14): {indicators['RSI']} ({rsi_s}) ---\n\n"
        f"--- Bollinger(20,2) ---\n"
        f"上轨: {indicators['Bollinger']['UPPER']}\n"
        f"中轨: {indicators['Bollinger']['MID']}\n"
        f"下轨: {indicators['Bollinger']['LOWER']}\n"
        f"带宽: {bbw:.1f}%\n\n"
        f"--- KDJ ---\n"
        f"K: {indicators['KDJ']['K']}  D: {indicators['KDJ']['D']}  J: {indicators['KDJ']['J']}\n\n"
        f"--- 其他 ---\n"
        f"ADX(趋势强度): {indicators['ADX']} ({'强趋势' if indicators['ADX']>25 else '弱趋势/盘整'})\n"
        f"ATR(波动率): {indicators['ATR']}\n"
        f"OBV(能量潮): {indicators['OBV']:,}\n"
        f"W%R(威廉指标): {indicators['WR']} ({'超卖' if indicators['WR']<-80 else '超买' if indicators['WR']>-20 else '中性'})\n\n"
        f"--- 成交量 ---\n"
        f"最新: {indicators['Volume']['latest']:,}\n"
        f"MA5: {indicators['Volume']['MA5']:,}  MA20: {indicators['Volume']['MA20']:,}"
    )

# ================================================================
# 公开接口
# ================================================================

def get_stock_data(code: str, mode: str = "all") -> str:
    """
    统一数据查询接口 (合并行情+技术+基本面)
    
    Args:
        code: 股票代码 (600519 / AAPL)
        mode: 'price'=行情, 'tech'=技术, 'fundamental'=基本面, 'all'=全部
    """
    market, norm, pure = _normalize(code)
    parts = []
    
    # 1. 实时行情 (所有模式都包含)
    try:
        data = _cb("tencent").call(_tencent_price, norm)
        parts.append(
            f"【{data['name']} ({code})】{data['price']} | "
            f"涨跌{data['change_pct']}% | PE{data.get('pe_ttm','?')} | "
            f"市值{data.get('market_cap_yi',0):.0f}亿 | "
            f"换手{data.get('turnover_rate',0)}% | "
            f"振{data.get('amplitude',0)}%"
        )
    except Exception as e:
        parts.append(f"[行情暂不可用: {e}]")
    
    # 2. 技术分析 (tech/all 模式)
    if mode in ("tech", "all") and market == "cn":
        # 尝试 akshare → 降级腾讯 K 线
        kline = None
        try:
            kline = _akshare_kline(pure)  # 主用
        except:
            pass
        if not kline:
            try:
                raw = _cb("tencent_k").call(_tencent_kline, norm)
                kline = raw
            except:
                pass
        if kline:
            closes = [float(x[2]) for x in kline]
            highs = [float(x[3]) for x in kline]
            lows = [float(x[4]) for x in kline]
            volumes = [int(x[5]) for x in kline]
            indicators = _calc_indicators(closes, highs, lows, volumes)
            parts.append(f"\n--- 技术指标 ---\n{_fmt_tech(code, closes[-1], indicators)}")
    
    # 3. 基本面 (fundamental/all 模式)
    if mode in ("fundamental", "all") and market == "cn":
        try:
            data = _cb("tencent").call(_tencent_price, norm)
            parts.append(f"\n--- 基本面 ---\n"
                f"PE(TTM): {data.get('pe_ttm','N/A')} | "
                f"市值: {data.get('market_cap_yi',0):.0f}亿 | "
                f"换手率: {data.get('turnover_rate',0)}% | "
                f"振幅: {data.get('amplitude',0)}%"
            )
        except:
            pass
    
    return "\n\n".join(parts) if parts else f"无 {code} 数据"


def get_market_info(indicator: str = "all") -> str:
    """
    市场信息 (情绪+新闻+排行)
    
    Args:
        indicator: 'all' / 'sentiment' / 'hot' / 'index'
    """
    parts = []
    
    # 市场情绪 (北向资金)
    if indicator in ("all", "sentiment"):
        try:
            import akshare as ak
            df = ak.stock_hsgt_fund_flow_summary_em()
            parts.append("=== 北向资金 ===")
            for _, row in df.iterrows():
                parts.append(
                    f"  {row['类型']} {row['板块']} {row['资金方向']}: "
                    f"净买={row.get('成交净买额','?')} "
                    f"↑{row.get('上涨数','?')} ↓{row.get('下跌数','?')}"
                )
        except:
            parts.append("[北向资金暂不可用]")
    
    # 热门排行
    if indicator in ("all", "hot"):
        try:
            import akshare as ak
            df = ak.stock_hot_search_baidu()
            parts.append("\n=== 热门股票 ===")
            for _, r in df.head(10).iterrows():
                parts.append(f"  {r['名称/代码']:12s} {r['涨跌幅']:>8s}  热度:{r['综合热度']}")
        except:
            pass
    
    # 大盘指数 (腾讯HTTP)
    if indicator in ("all", "index"):
        parts.append("\n=== 大盘指数 ===")
        for c, n in [("sh000001","上证"),("sz399001","深证"),("sh000688","科创50"),("sh000300","沪深300")]:
            try:
                r = requests.get(f"http://qt.gtimg.cn/q={c}", timeout=3)
                f = r.text.split("=")[1].strip('\";\n').split("~")
                parts.append(f"  {n}: {f[3]} ({f[32]}%)")
            except:
                pass
    
    return "\n".join(parts) if parts else "暂无市场信息"


def search_market_news(query: str, max_results: int = 5) -> str:
    """搜索新闻"""
    try:
        from src.plugins.plugin_collection.web.web import web_search
        return web_search(query, max_results=max_results)
    except Exception as e:
        return f"搜索失败: {e}"



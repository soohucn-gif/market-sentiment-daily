"""Market Temperature — 复刻长桥证券「市场温度指数」for US.

温度 = (估值百分位 + 情绪百分位) / 2，范围 0-100。

- 情绪百分位：当天「全美股上涨家数占比」在近 10 年的百分位。
  上涨家数占比 = (上涨 + 持平/2) / 总，**严格按长桥公式**，口径取
  NYSE + Nasdaq 全部挂牌 issues（$NYADV/$NYDEC/$NYTOT + $NAADV/$NADEC/$NATOT）。
  这是「当天」即时盘面温度，弥补 CNN F&G 几周回看的滞后。
  注：长桥涨跌家数口径更宽（含 OTC/ADR/优先股等，故其绝对家数更大，如 06-12
  长桥涨 6830 vs 本方 NYSE+Nasdaq 涨 4503），但**百分位对 issues 全集不敏感**——
  实测本方占比百分位与长桥情绪档位一致（同口径自比，相对位置稳定）。
- 估值百分位：S&P 500 TTM 市盈率（multpl，**市值加权**）当前值在近 10 年的百分位。
  ⚠️ 长桥用「全市场 PE 中位数」，但等权/中位数 PE 无免费 10 年历史源（multpl/
  Shiller 皆市值加权；RSP 等权 PE 在 GuruFocus/Zacks 付费墙）。市值加权 S&P500 PE
  被大盘科技股拉高，故本项会**系统性高于**长桥的中位数口径——这是已知的口径差，
  非数据错误。

数据源：StockCharts（涨跌家数）+ multpl.com（PE）。皆 curl（绕 TLS 指纹）。
失败回退 data/mtemp_seed.json。

历史曲线：对每个交易日，情绪百分位用全样本算，估值百分位用该日所在月的 PE 在
全 PE 样本算（月度 PE forward-fill 到日度），temp=两者均值。current = 末点。
"""
import re
import time
from urllib.parse import urlencode

from . import _net

SC_BASE = "https://stockcharts.com/c-sc/sc"
SC_STYLE = "p22657737025"  # public "Simple Line Chart" pcode
PE_URL = "https://www.multpl.com/s-p-500-pe-ratio/table/by-month"
WINDOW_YEARS = 10
_SEED_MAX_AGE_DAYS = 14

_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def percentile_rank(value: float, samples: list) -> float:
    """% of samples <= value (0-100). Empty samples -> neutral 50."""
    if not samples:
        return 50.0
    n = sum(1 for s in samples if s <= value)
    return round(n / len(samples) * 100, 1)


def _sc_series(symbol: str) -> dict:
    """StockCharts daily close for an 8-token OHLCV symbol -> {date: close}."""
    params = {
        "s": symbol, "p": "D", "yr": str(WINDOW_YEARS), "mn": "0", "dy": "0",
        "i": SC_STYLE, "img": "text", "inspector": "yes",
        "randomNumber": str(int(time.time() * 1000)),
    }
    body = _net.curl_get(f"{SC_BASE}?{urlencode(params)}", timeout=30)
    start, end = body.find(b"<pricedata>"), body.find(b"</pricedata>")
    if start == -1 or end == -1:
        raise RuntimeError(f"market_temp: StockCharts response missing <pricedata> for {symbol}")
    raw = body[start + len(b"<pricedata>"):end].decode("utf-8", errors="replace")
    out = {}
    for bar in raw.split("|"):
        parts = bar.split()
        if len(parts) != 8:  # idx, date_open, date_close, O, H, L, C, V; close = parts[6]
            continue
        d = parts[1][:8]
        out[f"{d[:4]}-{d[4:6]}-{d[6:8]}"] = float(parts[6])
    return out


def _fetch_breadth_ratio() -> list[dict]:
    """全美股(NYSE+Nasdaq)上涨家数占比 = (涨 + 平/2) / 总 → [{date, value(0-100)}] 升序。

    严格复刻长桥情绪口径。持平家数 = 总 - 涨 - 跌（StockCharts $NYUNCH 抓不到，
    用总减得；clamp >=0 防数据不一致）。
    """
    nyadv, nydec, nyt = _sc_series("$NYADV"), _sc_series("$NYDEC"), _sc_series("$NYTOT")
    naadv, nadec, nat = _sc_series("$NAADV"), _sc_series("$NADEC"), _sc_series("$NATOT")
    dates = set(nyadv) & set(nydec) & set(nyt) & set(naadv) & set(nadec) & set(nat)
    out = []
    for d in dates:
        adv = nyadv[d] + naadv[d]
        dec = nydec[d] + nadec[d]
        tot = nyt[d] + nat[d]
        if tot <= 0:
            continue
        unch = max(tot - adv - dec, 0.0)
        out.append({"date": d, "value": (adv + unch / 2) / tot * 100})
    out.sort(key=lambda h: h["date"])
    if not out:
        raise RuntimeError("market_temp: empty breadth ratio series")
    return out


def _fetch_pe() -> list[dict]:
    """multpl monthly S&P500 TTM PE -> [{date, pe}] ascending (recent WINDOW_YEARS+ only)."""
    html = _net.curl_get(PE_URL, timeout=30).decode("utf-8", errors="replace")
    rows = re.findall(r"<td>([A-Z][a-z]{2} \d{1,2}, \d{4})</td>\s*<td>(.*?)</td>", html, re.DOTALL)
    out = []
    for date_str, raw in rows:
        m = re.search(r"\d+\.\d+", raw)
        if not m:
            continue
        mon, day, yr = re.match(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})", date_str).groups()
        iso = f"{yr}-{_MONTHS[mon]:02d}-{int(day):02d}"
        out.append({"date": iso, "pe": float(m.group())})
    if not out:
        raise RuntimeError("market_temp: could not parse any PE rows from multpl")
    out.sort(key=lambda h: h["date"])
    return out[-(WINDOW_YEARS * 12 + 18):]  # ~WINDOW_YEARS of monthly points for the pool


def _fetch_live() -> dict:
    breadth = _fetch_breadth_ratio()
    pe = _fetch_pe()
    if not breadth or not pe:
        raise RuntimeError("market_temp: empty breadth or PE series")

    br_samples = [p["value"] for p in breadth]
    pe_samples = [p["pe"] for p in pe]

    pe_dates = [p["date"] for p in pe]
    pe_vals = [p["pe"] for p in pe]

    def pe_asof(day: str) -> float:
        lo, hi, found = 0, len(pe_dates) - 1, pe_vals[0]
        while lo <= hi:
            mid = (lo + hi) // 2
            if pe_dates[mid] <= day:
                found = pe_vals[mid]
                lo = mid + 1
            else:
                hi = mid - 1
        return found

    history = []
    for p in breadth:
        emo = percentile_rank(p["value"], br_samples)
        val = percentile_rank(pe_asof(p["date"]), pe_samples)
        history.append({"date": p["date"], "value": round((emo + val) / 2, 1)})

    last = breadth[-1]
    cur_pe = pe[-1]["pe"]
    emotion_pct = percentile_rank(last["value"], br_samples)
    valuation_pct = percentile_rank(cur_pe, pe_samples)
    return {
        "status": "ok",
        "current": {
            "value": round((emotion_pct + valuation_pct) / 2, 1),
            "date": last["date"],
            "emotion_pct": emotion_pct,
            "valuation_pct": valuation_pct,
            "adv_ratio": round(last["value"], 1),  # 全美股当天上涨家数占比 %
            "pe": round(cur_pe, 2),
        },
        "history": history,
    }


def fetch():
    try:
        payload = _fetch_live()
        _net.save_seed("mtemp", payload)
        return payload
    except Exception as live_err:
        seeded = _net.load_seed("mtemp", _SEED_MAX_AGE_DAYS)
        if seeded is not None:
            return seeded
        raise live_err

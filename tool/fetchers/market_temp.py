"""Market Temperature — 复刻长桥证券「市场温度指数」for US (S&P 500).

温度 = (估值百分位 + 情绪百分位) / 2，范围 0-100。

- 情绪百分位：当天 S&P 500 涨跌广度 $SPXADP（= (上涨家数-下跌家数)/总家数×100，
  -100~+100）在近 10 年历史中的百分位。这是「当天」即时盘面温度，弥补 CNN F&G
  几周回看的滞后。$SPXADP 与长桥「上涨家数占比」是单调等价（百分位对单调变换不变）。
- 估值百分位：S&P 500 TTM 市盈率（GAAP，multpl.com）当前值在近 10 年的百分位。
  慢变量，反映「贵不贵」。

数据源：StockCharts $SPXADP（SharpCharts inspector，同 breadth.py 模式）+
multpl.com 月度 PE 表。两者皆 curl（绕 TLS 指纹）。失败回退 data/mtemp_seed.json。

历史曲线：对每个交易日，情绪百分位用全样本算，估值百分位用该日所在月的 PE 在
全 PE 样本算（月度 PE forward-fill 到日度），temp=两者均值。current = 末点。
"""
import re
import time
from urllib.parse import urlencode

from . import _net

SC_BASE = "https://stockcharts.com/c-sc/sc"
SC_STYLE = "p22657737025"  # public "Simple Line Chart" pcode
SPXADP_SYMBOL = "$SPXADP"
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


def _fetch_spxadp() -> list[dict]:
    """StockCharts $SPXADP daily bars -> [{date, value(-100~100)}] ascending."""
    params = {
        "s": SPXADP_SYMBOL, "p": "D", "yr": str(WINDOW_YEARS), "mn": "0", "dy": "0",
        "i": SC_STYLE, "img": "text", "inspector": "yes",
        "randomNumber": str(int(time.time() * 1000)),
    }
    body = _net.curl_get(f"{SC_BASE}?{urlencode(params)}", timeout=30)
    start, end = body.find(b"<pricedata>"), body.find(b"</pricedata>")
    if start == -1 or end == -1:
        raise RuntimeError("market_temp: StockCharts response missing <pricedata> for $SPXADP")
    raw = body[start + len(b"<pricedata>"):end].decode("utf-8", errors="replace")
    out = []
    for bar in raw.split("|"):
        parts = bar.split()
        # $SPXADP bars are 8-token OHLCV (idx, date_open, date_close, O, H, L, C, V); close = parts[6]
        if len(parts) != 8:
            continue
        d = parts[1][:8]
        out.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:8]}", "value": float(parts[6])})
    out.sort(key=lambda h: h["date"])
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
    # keep a bit more than WINDOW_YEARS of monthly points for the percentile pool
    return out[-(WINDOW_YEARS * 12 + 18):]


def _fetch_live() -> dict:
    adp = _fetch_spxadp()
    pe = _fetch_pe()
    if not adp or not pe:
        raise RuntimeError("market_temp: empty SPXADP or PE series")

    adp_samples = [p["value"] for p in adp]
    pe_samples = [p["pe"] for p in pe]

    # forward-fill: most recent PE with pe_date <= each trading day
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
    for p in adp:
        emo = percentile_rank(p["value"], adp_samples)
        val = percentile_rank(pe_asof(p["date"]), pe_samples)
        history.append({"date": p["date"], "value": round((emo + val) / 2, 1)})

    last_adp = adp[-1]
    cur_pe = pe[-1]["pe"]
    emotion_pct = percentile_rank(last_adp["value"], adp_samples)
    valuation_pct = percentile_rank(cur_pe, pe_samples)
    return {
        "status": "ok",
        "current": {
            "value": round((emotion_pct + valuation_pct) / 2, 1),
            "date": last_adp["date"],
            "emotion_pct": emotion_pct,
            "valuation_pct": valuation_pct,
            "spxadp": round(last_adp["value"], 1),
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

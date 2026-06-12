"""VIX fetcher (S&P 500 30-day implied volatility, CASH index close — not /VX futures).

Source chain (2026-06-12 redesign after a data-accuracy incident):
1. CBOE official VIX_History.csv (cdn.cboe.com) — first-party EOD file,
   contains ONLY settled daily closes, so it can never serve an
   in-progress intraday print as a "close".
2. Yahoo v8 chart API — near-real-time but its last daily bar is the
   LIVE in-progress value during (extended) trading hours. We drop the
   last bar unless it is a settled close (bar date < today in
   US/Eastern, or after 16:15 ET on bar date). The 2026-06-10 incident:
   a 03:42 ET extended-hours print (20.25) was recorded as the day's
   close (real close: 22.22) and then frozen into the seed for 2 days.
3. FRED VIXCLS — datacenter-friendly, ~1 trading day lag.
4. Committed seed (annotated stale).

All transports via system curl (see _net) — Python TLS gets blocked
from datacenter IPs.
"""
import csv
import io
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import _net

CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
    "?range=max&interval=1d"
)
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"
_SEED_MAX_AGE_DAYS = 14
_ET = ZoneInfo("America/New_York")


def _fetch_cboe() -> list[dict]:
    text = _net.curl_get(CBOE_URL, timeout=30).decode("utf-8", errors="replace")
    history = []
    for row in csv.DictReader(io.StringIO(text)):
        # Columns: DATE (MM/DD/YYYY), OPEN, HIGH, LOW, CLOSE
        d = row.get("DATE", "")
        c = row.get("CLOSE", "")
        if not d or not c:
            continue
        try:
            mm, dd, yyyy = d.split("/")
            history.append({"date": f"{yyyy}-{mm}-{dd}", "value": round(float(c), 2)})
        except ValueError:
            continue
    history.sort(key=lambda h: h["date"])
    return history


def _drop_unsettled_last_bar(history: list[dict]) -> list[dict]:
    """Remove the trailing bar if it's an in-progress (not settled) session.

    Yahoo's last daily bar mirrors the live print during US (extended)
    hours. A bar only counts as a close once it is yesterday-or-older in
    ET, or today after 16:15 ET.
    """
    if not history:
        return history
    now_et = datetime.now(_ET)
    last_date = history[-1]["date"]
    today_et = now_et.strftime("%Y-%m-%d")
    if last_date == today_et and (now_et.hour, now_et.minute) < (16, 15):
        return history[:-1]
    return history


def _fetch_yahoo() -> list[dict]:
    raw = json.loads(_net.curl_get(YAHOO_URL, headers={"Accept": "application/json"}, timeout=30))
    result = raw["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    history = [
        {
            "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            "value": round(float(c), 2),
        }
        for ts, c in zip(timestamps, closes)
        if c is not None
    ]
    history.sort(key=lambda h: h["date"])
    return _drop_unsettled_last_bar(history)


def _fetch_fred() -> list[dict]:
    text = _net.curl_get(FRED_URL, timeout=30).decode("utf-8", errors="replace")
    history = []
    for row in csv.DictReader(io.StringIO(text)):
        # Columns: observation_date, VIXCLS ('.' for missing days)
        value = row.get("VIXCLS", ".")
        date = row.get("observation_date") or row.get("DATE", "")
        if value in (".", "", None) or not date:
            continue
        history.append({"date": date, "value": round(float(value), 2)})
    history.sort(key=lambda h: h["date"])
    return history


def _fetch_live() -> dict:
    history = []
    source = None
    for fn, name in ((_fetch_cboe, "cboe"), (_fetch_yahoo, "yahoo"), (_fetch_fred, "fred")):
        try:
            history = fn()
            if history:
                source = name
                break
        except Exception:
            continue
    if not history:
        raise RuntimeError("vix: CBOE, Yahoo and FRED all returned nothing")
    return {
        "status": "ok",
        "current": {"value": history[-1]["value"], "date": history[-1]["date"]},
        "history": history,
        "source": source,
    }


def fetch():
    try:
        payload = _fetch_live()
        _net.save_seed("vix", payload)
        return payload
    except Exception as live_err:
        seeded = _net.load_seed("vix", _SEED_MAX_AGE_DAYS)
        if seeded is not None:
            return seeded
        raise live_err

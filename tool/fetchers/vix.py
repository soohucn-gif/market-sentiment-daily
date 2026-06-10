"""VIX fetcher.

Primary: Yahoo Finance v8 chart API via system curl (see _net) — yfinance
was dropped because its Python TLS gets blocked from datacenter IPs and
its failure mode is an opaque TypeError. Secondary: FRED's VIXCLS series
(St. Louis Fed, datacenter-friendly, ~1 trading day lag). Tertiary: the
committed seed.
"""
import csv
import io
import json
from datetime import datetime, timezone

from . import _net

YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
    "?range=max&interval=1d"
)
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"
_SEED_MAX_AGE_DAYS = 14


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
    return history


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
    try:
        history = _fetch_yahoo()
    except Exception:
        history = _fetch_fred()
    if not history:
        raise RuntimeError("vix: both Yahoo and FRED returned empty series")
    return {
        "status": "ok",
        "current": {"value": history[-1]["value"], "date": history[-1]["date"]},
        "history": history,
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

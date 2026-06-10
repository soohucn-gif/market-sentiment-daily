"""AAII Investor Sentiment Survey fetcher.

Source: weekly XLS published on aaii.com. The sheet has a 3-row preamble
(merged org address, sub-header label, header label) before the column
header row; `skiprows=3` lands the dataframe on clean column names
(`Date`, `Bullish`, `Neutral`, `Bearish`, ...). Values are stored as
decimals (0.42 = 42%); we normalize to percent. Trailing rows like
`Count '24` are sentinel summary rows -- discarded by `to_datetime(errors='coerce')`
followed by `dropna`.

WAF note: aaii.com sits behind Imperva/Incapsula, which fingerprints TLS
handshakes AND throttles by IP. Python `requests` (urllib3/openssl) is
permanently flagged as a bot; system `curl` works from cold but the IP
gets challenged after repeated rapid requests. AAII publishes weekly,
so a slightly-stale read is functionally identical to a fresh one. We
therefore: (1) shell out to `curl` to bypass TLS fingerprinting on the
happy path, and (2) cache the last successful parse to disk so that any
future WAF challenge falls back to the cached payload (flagged
`stale_since_iso`) rather than failing the indicator outright.
"""
import io
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import _net

URL = "https://www.aaii.com/files/surveys/sentiment.xls"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# CDFV2 (legacy XLS) magic bytes. HTML challenge pages start with `<`.
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"

# Disk cache: persisted after every successful fetch, read as fallback when
# the live fetch fails. AAII updates weekly so even a 14-day-old cache is
# usable; older than that and we'd rather surface the error than mislead.
_CACHE_PATH = Path(__file__).parent.parent / ".cache" / "aaii_last_good.json"
_CACHE_MAX_AGE_DAYS = 14
# Committed seed (via _net helpers, data/aaii_seed.json): refreshed on every
# successful fetch from an Imperva-accepted IP. Lets cloud runners
# (datacenter IPs that Imperva blocks outright) still render the
# latest-known weekly data. Longer leash than the live cache since cloud
# refreshes may never succeed.
_SEED_MAX_AGE_DAYS = 45


def _to_pct(v):
    # AAII publishes as decimals (0.42 = 42%); normalize to percent.
    if v is None or v != v:
        return None
    v = float(v)
    return round(v * 100, 2) if v <= 1.0 else round(v, 2)


def _fetch_xls_bytes() -> bytes:
    """Fetch raw XLS bytes via system `curl` (works past Imperva fingerprinting).

    Raises RuntimeError if curl exits non-zero, the response isn't a CDFV2 XLS,
    or the file is implausibly small (Imperva HTML challenge is ~4.5KB; real
    XLS is ~1.1MB).
    """
    try:
        result = subprocess.run(
            [
                "curl", "-sS", "--fail", "--max-time", "30",
                "-A", UA,
                "-H", "Accept: application/vnd.ms-excel,application/octet-stream,*/*;q=0.8",
                "-H", "Accept-Language: en-US,en;q=0.9",
                "-H", "Referer: https://www.aaii.com/sentimentsurvey",
                URL,
            ],
            capture_output=True,
            check=True,
            timeout=35,
        )
    except FileNotFoundError as e:
        raise RuntimeError("aaii: `curl` not found on PATH (required for WAF bypass)") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"aaii: curl exited {e.returncode}: {e.stderr.decode(errors='replace')[:200]}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("aaii: curl timed out after 35s") from e

    data = result.stdout
    if not data.startswith(_XLS_MAGIC):
        # Most likely the WAF served the JS challenge HTML; surface a clear hint.
        preview = data[:80].decode(errors="replace")
        raise RuntimeError(
            f"aaii: response is not an XLS (got {len(data)} bytes starting with {preview!r}) -- "
            "WAF may be challenging this IP; try again in a few minutes"
        )
    return data


def _parse_xls(raw: bytes) -> dict:
    df = pd.read_excel(io.BytesIO(raw), sheet_name=0, skiprows=3, engine="xlrd")
    df.columns = [str(c).strip() for c in df.columns]

    # Tolerant column detection. `Mov Avg` and `+St. Dev.` columns also exist;
    # explicit exact-match keeps us on the raw weekly Bullish/Neutral/Bearish
    # columns instead of derived series.
    date_col = next(c for c in df.columns if c.lower() == "date")
    bull_col = next(c for c in df.columns if c.lower() == "bullish")
    neut_col = next(c for c in df.columns if c.lower() == "neutral")
    bear_col = next(c for c in df.columns if c.lower() == "bearish")

    df = df[[date_col, bull_col, neut_col, bear_col]].dropna(subset=[date_col])
    df = df.rename(columns={date_col: "date", bull_col: "bull", neut_col: "neut", bear_col: "bear"})
    # Trailing summary rows (e.g. `Count '24`) become NaT here and get dropped.
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")

    def series(col):
        return [
            {"date": row["date"].strftime("%Y-%m-%d"), "value": _to_pct(row[col])}
            for _, row in df.iterrows()
            if _to_pct(row[col]) is not None
        ]

    bullish, neutral, bearish = series("bull"), series("neut"), series("bear")
    if not bullish or not neutral or not bearish:
        raise RuntimeError("aaii: empty series after parsing")
    return {
        "status": "ok",
        "current": {
            "bullish": bullish[-1]["value"],
            "neutral": neutral[-1]["value"],
            "bearish": bearish[-1]["value"],
            "date": bullish[-1]["date"],
        },
        "bullish": bullish,
        "neutral": neutral,
        "bearish": bearish,
    }


def _save_cache(payload: dict) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "saved_at_iso": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        _CACHE_PATH.write_text(json.dumps(envelope, ensure_ascii=False))
    except OSError:
        # Cache write is best-effort; don't fail the fetch because of it.
        pass


def _load_cache(max_age_days: float) -> dict | None:
    """Return the payload from the live-cache envelope (annotated) or None."""
    try:
        envelope = json.loads(_CACHE_PATH.read_text())
        saved_at = datetime.fromisoformat(envelope["saved_at_iso"])
        age_days = (datetime.now(timezone.utc) - saved_at).total_seconds() / 86400
        if age_days > max_age_days:
            return None
        payload = dict(envelope["payload"])  # shallow copy
        payload["stale_since_iso"] = envelope["saved_at_iso"]
        return payload
    except (OSError, ValueError, KeyError):
        return None


def fetch():
    """Fetch fresh data on the happy path; fall back to disk cache, then seed."""
    try:
        raw = _fetch_xls_bytes()
        payload = _parse_xls(raw)
        _save_cache(payload)
        _net.save_seed("aaii", payload)
        return payload
    except Exception as live_err:
        cached = _load_cache(_CACHE_MAX_AGE_DAYS)
        if cached is not None:
            return cached
        seeded = _net.load_seed("aaii", _SEED_MAX_AGE_DAYS)
        if seeded is not None:
            return seeded
        # No fallback available -- surface the live error to the caller.
        raise live_err

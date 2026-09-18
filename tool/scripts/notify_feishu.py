"""Send today's market sentiment summary to Feishu via custom-bot webhook.

Usage:
    python3 tool/scripts/notify_feishu.py <data_json_path> [date]
    python3 tool/scripts/notify_feishu.py data.json 2026-09-18

Requires env var FEISHU_WEBHOOK_URL  (from the routine's environment config).
Exit 0 = sent OK; exit 1 = webhook not configured or send failed.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


WEATHER = {
    (75, 101): "☀️大太阳",
    (50, 75):  "🌤晴天",
    (25, 50):  "☁️阴天",
    (0, 25):   "❄️暴风雪",
}


def _weather(v):
    for (lo, hi), label in WEATHER.items():
        if lo <= v < hi:
            return label
    return ""


def _fmt(v, decimals=1):
    if v is None:
        return "失效"
    return f"{v:.{decimals}f}"


def build_message(data: dict, date_str: str) -> str:
    mm_dd = date_str[5:]  # "09-18"
    inds = data.get("indicators", {})

    def cur(name, key=None):
        v = inds.get(name, {}).get("current", {})
        if not v:
            return None
        return v.get(key) if key else v

    def is_stale(name):
        return bool(inds.get(name, {}).get("stale_since_iso"))

    def status_ok(name):
        return inds.get(name, {}).get("status") == "ok"

    # Counts
    live = sum(1 for k, v in inds.items() if v.get("status") == "ok" and not v.get("stale_since_iso"))
    seeded = sum(1 for k, v in inds.items() if v.get("status") == "ok" and v.get("stale_since_iso"))
    failed = sum(1 for v in inds.values() if v.get("status") == "error")

    # Values
    sdtoken_v = cur("sdtoken", "value")
    fng_v = cur("fng", "value")
    vix_v = cur("vix", "value")
    aaii_cur = cur("aaii") or {}
    bullish = aaii_cur.get("bullish")
    bearish = aaii_cur.get("bearish")
    aaii_spread = round(bullish - bearish, 1) if bullish is not None and bearish is not None else None
    putcall_v = cur("putcall", "value")
    breadth_v = cur("breadth", "ndx")

    weather = _weather(fng_v) if fng_v is not None else ""

    token_str = f"Token{_fmt(sdtoken_v)}" if sdtoken_v is not None else "Token失效"
    fng_str = f"F&G{_fmt(fng_v, 0)}{weather}" if fng_v is not None else "F&G失效"
    vix_str = f"VIX{_fmt(vix_v)}" if vix_v is not None else "VIX失效"
    aaii_str = (f"AAII{'+' if aaii_spread and aaii_spread > 0 else ''}{_fmt(aaii_spread)}"
                if aaii_spread is not None else "AAII失效")
    pc_str = f"P/C{_fmt(putcall_v)}" if putcall_v is not None else "P/C失效"
    breadth_str = f"广度{_fmt(breadth_v, 0)}%" if breadth_v is not None else "广度失效"

    tail = f"{live}活/{seeded}种子"
    if failed:
        tail += f"（{failed}失效）"

    url = "https://soohucn-gif.github.io/market-sentiment-daily/"
    line = (
        f"美股情绪 {mm_dd}｜"
        f"{token_str} {fng_str} {vix_str} {aaii_str} {pc_str} {breadth_str}"
        f"｜{tail}\n{url}"
    )
    return line


def send(webhook_url: str, text: str) -> bool:
    """Send text message via Feishu custom-bot webhook. Returns True on success."""
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}, ensure_ascii=False)
    cmd = [
        "curl", "-sS", "--fail", "--max-time", "15",
        "-H", "Content-Type: application/json",
        "-d", payload,
        webhook_url,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        err = result.stderr.decode(errors="replace").strip()[:200]
        print(f"[notify_feishu] curl failed: {err}", file=sys.stderr)
        return False
    resp = result.stdout.decode(errors="replace")
    try:
        body = json.loads(resp)
        if body.get("code", 0) != 0 or body.get("StatusCode", 0) != 0:
            print(f"[notify_feishu] Feishu error: {resp[:200]}", file=sys.stderr)
            return False
    except Exception:
        pass
    return True


def main():
    webhook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook:
        print("[notify_feishu] FEISHU_WEBHOOK_URL not set — skipping Feishu notification.", file=sys.stderr)
        sys.exit(1)

    data_path = sys.argv[1] if len(sys.argv) > 1 else "data.json"
    date_str = sys.argv[2] if len(sys.argv) > 2 else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    data = json.loads(Path(data_path).read_text())
    msg = build_message(data, date_str)
    print(f"[notify_feishu] Sending:\n{msg}")

    ok = send(webhook, msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

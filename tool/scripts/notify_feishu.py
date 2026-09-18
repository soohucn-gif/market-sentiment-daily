"""Send today's market sentiment summary via Feishu self-built app (direct message).

Usage:
    python3 tool/scripts/notify_feishu.py <data_json_path> [date]
    python3 tool/scripts/notify_feishu.py data.json 2026-09-18

Auth flow (same as Macro5 routine):
    1. POST /auth/v3/tenant_access_token/internal  (APP_ID + APP_SECRET)
    2. POST /im/v1/messages?receive_id_type=open_id  (tenant_token + OPEN_ID)

Required env var:
    FEISHU_APP_SECRET   32-char secret for the Feishu self-built app

Optional env vars (non-secret; defaults shown):
    FEISHU_APP_ID       cli_aaa0ea50ff781beb
    FEISHU_OPEN_ID      ou_5703cc20f1db48bb4cf00b07eebc0d93

Exit 0 = sent OK; exit 1 = missing secret or send failed.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_FEISHU_BASE = "https://open.feishu.cn/open-apis"
_DEFAULT_APP_ID = "cli_aaa0ea50ff781beb"
_DEFAULT_OPEN_ID = "ou_5703cc20f1db48bb4cf00b07eebc0d93"

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
    return (
        f"美股情绪 {mm_dd}｜"
        f"{token_str} {fng_str} {vix_str} {aaii_str} {pc_str} {breadth_str}"
        f"｜{tail}\n{url}"
    )


def _curl_post(url: str, payload: str, headers: list[str]) -> tuple[int, str]:
    """Run curl POST, return (returncode, response_body)."""
    cmd = ["curl", "-sS", "--fail", "--max-time", "15"]
    for h in headers:
        cmd += ["-H", h]
    cmd += ["-d", payload, url]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode, result.stdout.decode(errors="replace")


def get_tenant_token(app_id: str, app_secret: str) -> str:
    """Exchange APP_ID + APP_SECRET for a 2-hour tenant_access_token."""
    payload = json.dumps({"app_id": app_id, "app_secret": app_secret})
    rc, body = _curl_post(
        f"{_FEISHU_BASE}/auth/v3/tenant_access_token/internal",
        payload,
        ["Content-Type: application/json"],
    )
    if rc != 0:
        raise RuntimeError(f"feishu auth curl failed (exit {rc})")
    data = json.loads(body)
    if data.get("code", -1) != 0:
        raise RuntimeError(f"feishu auth error: {body[:200]}")
    return data["tenant_access_token"]


def send_message(tenant_token: str, open_id: str, text: str) -> bool:
    """Send a text message to open_id. Returns True on success."""
    # Feishu /im/v1/messages requires `content` to be a JSON-encoded string.
    content = json.dumps({"text": text}, ensure_ascii=False)
    payload = json.dumps(
        {"receive_id": open_id, "msg_type": "text", "content": content},
        ensure_ascii=False,
    )
    rc, body = _curl_post(
        f"{_FEISHU_BASE}/im/v1/messages?receive_id_type=open_id",
        payload,
        [
            "Content-Type: application/json",
            f"Authorization: Bearer {tenant_token}",
        ],
    )
    if rc != 0:
        print(f"[notify_feishu] curl failed (exit {rc}): {body[:200]}", file=sys.stderr)
        return False
    data = json.loads(body)
    if data.get("code", -1) != 0:
        print(f"[notify_feishu] Feishu API error: {body[:300]}", file=sys.stderr)
        return False
    return True


def main():
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_secret:
        print("[notify_feishu] FEISHU_APP_SECRET not set — skipping.", file=sys.stderr)
        sys.exit(1)

    app_id = os.environ.get("FEISHU_APP_ID", _DEFAULT_APP_ID).strip()
    open_id = os.environ.get("FEISHU_OPEN_ID", _DEFAULT_OPEN_ID).strip()

    data_path = sys.argv[1] if len(sys.argv) > 1 else "data.json"
    date_str = sys.argv[2] if len(sys.argv) > 2 else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    data = json.loads(Path(data_path).read_text())
    msg = build_message(data, date_str)
    print(f"[notify_feishu] Sending:\n{msg}")

    try:
        token = get_tenant_token(app_id, app_secret)
    except Exception as e:
        print(f"[notify_feishu] Failed to get tenant token: {e}", file=sys.stderr)
        sys.exit(1)

    ok = send_message(token, open_id, msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

"""Generate a self-contained static snapshot of the sentiment dashboard.

Runs all 6 fetchers once, then assembles a single HTML file with the data
payload, CSS, and JS inlined — viewable anywhere (GitHub Pages, local file)
with no Flask server. ECharts stays on CDN.

Outputs (under dist/):
- index.html                 latest snapshot
- archive/YYYY-MM-DD.html    dated copy (Asia/Shanghai date)
- data.json                  raw payload (consumed by the notify routine)

Usage: python scripts/generate_static.py [OUT_DIR]
  OUT_DIR defaults to <tool>/dist. The cloud routine passes the public
  repo root so index.html / archive/ / data.json land where GitHub
  Pages serves them.
Exit codes: 0 = generated (possibly with some failed indicators);
            1 = ALL indicators failed (nothing worth publishing).
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def build_static_html(template: str, css: str, js: str, payload: dict) -> str:
    """Inline css + payload + js into the Flask template's HTML."""
    # `</` would terminate the inline <script> early (e.g. an error_msg
    # containing "</script>"); escape it inside the JSON string.
    payload_json = json.dumps(payload, ensure_ascii=False, indent=1).replace("</", "<\\/")

    html = re.sub(
        r'<link rel="stylesheet"[^>]*>',
        lambda m: f"<style>\n{css}\n</style>",
        template,
        count=1,
    )
    inline = (
        f"<script>window.__PRELOADED__ = {payload_json};</script>\n"
        f"<script>\n{js}\n</script>"
    )
    html = re.sub(
        r'<script src="[^"]*app\.js[^"]*"></script>',
        lambda m: inline,
        html,
        count=1,
    )
    return html


def main() -> int:
    from app import gather_indicators

    print("Fetching all indicators (force refresh)...")
    payload = gather_indicators(force=True)
    statuses = {k: v["status"] for k, v in payload["indicators"].items()}
    for key, status in sorted(statuses.items()):
        marker = "OK " if status == "ok" else "ERR"
        extra = ""
        if status != "ok":
            extra = " — " + payload["indicators"][key].get("error_msg", "?")[:90]
        print(f"  [{marker}] {key}{extra}")

    ok_count = sum(1 for s in statuses.values() if s == "ok")
    if ok_count == 0:
        print("All indicators failed — refusing to publish an empty dashboard.")
        return 1

    template = (ROOT / "templates" / "index.html").read_text()
    css = (ROOT / "static" / "style.css").read_text()
    js = (ROOT / "static" / "app.js").read_text()
    html = build_static_html(template, css, js, payload)

    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist"
    (out / "archive").mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html)
    bj_date = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    (out / "archive" / f"{bj_date}.html").write_text(html)
    (out / "data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))

    print(f"Generated {out}/index.html + archive/{bj_date}.html ({ok_count}/{len(statuses)} indicators ok)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Silicon Data LLM Token Expenditure Index — manually curated local series.

No free structured source exists: Silicon Data's Token Index API
(docs.silicondata.com, POST /api/token-index/index) is a paid OAuth2
product, and Bloomberg/Macrobond carry the index under terminal licenses
only. We therefore maintain a curated series in
`data/silicon_data_index.json`, sourced from Silicon Data's public posts
(X @Silicon_Data, LinkedIn) and press coverage, each point dated and
source-attributed. Points derived arithmetically (e.g. backed out of a
reported percent change) are flagged `estimated: true`.

Update workflow: run /update-silicon-data in a Claude session — Claude
searches the latest publicly reported values and appends them. The
dashboard then picks the new points up on the next refresh.

Index meaning: usage-weighted average price paid per 1M LLM tokens across
the whole market — the marginal willingness to pay for LLMs. Rising =
migration to expensive frontier models; falling = migration to cheap
open-weight models.
"""
import json
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data" / "silicon_data_index.json"


def fetch():
    raw = json.loads(DATA_PATH.read_text())
    points = sorted(raw["points"], key=lambda p: p["date"])
    if not points:
        raise RuntimeError("silicon_data: no points in data file")

    history = [{"date": p["date"], "value": float(p["value"])} for p in points]
    return {
        "status": "ok",
        "current": {"value": history[-1]["value"], "date": history[-1]["date"]},
        "history": history,
        "updated_at": raw.get("updated_at"),
        "estimated_dates": [p["date"] for p in points if p.get("estimated")],
        "milestones": raw.get("milestones", []),
    }

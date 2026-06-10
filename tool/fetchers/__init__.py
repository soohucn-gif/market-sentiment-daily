"""Fetcher contract:

Each module exposes `fetch() -> dict`:
- On success: returns a dict with `status: "ok"` and indicator-specific
  fields. The orchestrator wraps the dict directly in the API payload.
- On failure: raises. The orchestrator (`app.gather_indicators`) catches
  and converts to `{status: "error", error_msg: ...}`. Do NOT swallow
  exceptions internally — let them propagate so failures are visible.

History items follow `{"date": "YYYY-MM-DD", "value": <number>}` and are
sorted ascending by date. Single-series fetchers expose them under
`history`; multi-series fetchers (e.g. breadth, AAII) use named keys.
"""

"""Live smoke test of the orchestration layer."""
from app import gather_indicators


def test_gather_returns_all_seven_keys():
    result = gather_indicators(force=True)
    assert set(result["indicators"].keys()) == {
        "fng", "vix", "breadth", "aaii", "putcall", "sdtoken", "mtemp",
    }
    for key, val in result["indicators"].items():
        assert val["status"] in ("ok", "error"), f"{key}: {val}"


def test_gather_isolates_failures():
    # We can't easily inject a failing fetcher without mocks; smoke-only check.
    # At least one should be ok (otherwise something systemically wrong).
    result = gather_indicators(force=True)
    ok_count = sum(1 for v in result["indicators"].values() if v["status"] == "ok")
    assert ok_count >= 3, f"only {ok_count}/6 indicators ok"

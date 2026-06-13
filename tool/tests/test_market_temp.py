"""Market Temperature fetcher tests.

percentile_rank is a pure function — deterministic offline tests.
fetch() hits StockCharts ($SPXADP) + multpl (S&P PE) live — smoke test.
"""
from fetchers.market_temp import percentile_rank
from fetchers import market_temp


def test_percentile_rank_basic():
    s = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert percentile_rank(5, s) == 50.0   # 5 of 10 are <= 5
    assert percentile_rank(10, s) == 100.0
    assert percentile_rank(1, s) == 10.0


def test_percentile_rank_empty_is_neutral():
    assert percentile_rank(5, []) == 50.0


def test_percentile_rank_above_all():
    assert percentile_rank(99, [1, 2, 3]) == 100.0


def test_market_temp_live():
    d = market_temp.fetch()
    assert d["status"] == "ok"
    cur = d["current"]
    assert 0 <= cur["value"] <= 100
    assert 0 <= cur["valuation_pct"] <= 100
    assert 0 <= cur["emotion_pct"] <= 100
    # temp is the mean of its two components
    assert abs(cur["value"] - (cur["valuation_pct"] + cur["emotion_pct"]) / 2) < 0.6
    assert -100 <= cur["spxadp"] <= 100
    assert cur["pe"] > 0
    assert len(d["history"]) > 500
    assert d["history"][0]["date"] < d["history"][-1]["date"]
    assert all(0 <= p["value"] <= 100 for p in d["history"])

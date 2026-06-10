import time
from cache import TTLCache


def test_cache_returns_value_within_ttl():
    c = TTLCache(ttl_seconds=10)
    c.set("k", {"v": 1})
    assert c.get("k") == {"v": 1}


def test_cache_expires_after_ttl():
    c = TTLCache(ttl_seconds=0.05)
    c.set("k", "v")
    time.sleep(0.1)
    assert c.get("k") is None


def test_cache_miss_returns_none():
    c = TTLCache(ttl_seconds=10)
    assert c.get("missing") is None

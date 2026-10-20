import pytest

from responder.ratelimit import LimitExceeded, Limiter


class FakeRedis(Limiter):
    """A Limiter whose Redis is a dict, so the shared-store logic runs with no network."""
    def __init__(self, **kw):
        super().__init__(url="https://fake.upstash.io", token="t", **kw)
        self.store, self.ttls, self.fail = {}, {}, False

    def _redis(self, *cmd):
        if self.fail:
            raise OSError("redis down")
        if cmd[0] == "PING":
            return "PONG"
        op, key, *rest = cmd
        if op == "INCR":
            self.store[key] = self.store.get(key, 0) + 1
            return self.store[key]
        if op == "EXPIRE":
            self.ttls[key] = rest[0]
            return 1


def test_hourly_limit_is_per_visitor():
    lim = FakeRedis(hourly=2, daily=100)
    lim.check("1.1.1.1"); lim.check("1.1.1.1")
    with pytest.raises(LimitExceeded) as e:
        lim.check("1.1.1.1")
    assert e.value.reason == "hourly"
    lim.check("2.2.2.2")  # someone else is unaffected


def test_daily_cap_is_shared_across_visitors():
    lim = FakeRedis(hourly=10, daily=3)
    for ip in ("a", "b", "c"):
        lim.check(ip)
    with pytest.raises(LimitExceeded) as e:
        lim.check("d")
    assert e.value.reason == "daily"


def test_blocked_visitors_do_not_use_up_the_daily_budget():
    lim = FakeRedis(hourly=1, daily=100)
    lim.check("a")
    for _ in range(5):
        with pytest.raises(LimitExceeded):
            lim.check("a")
    day_keys = [k for k in lim.store if k.startswith("rl:d:")]
    assert lim.store[day_keys[0]] == 1


def test_keys_have_expiry_and_never_contain_the_raw_ip():
    lim = FakeRedis(hourly=5, daily=5)
    lim.check("203.0.113.7")
    assert all("203.0.113.7" not in k for k in lim.store)
    assert set(lim.ttls) == set(lim.store)  # every counter expires on its own


def test_redis_failure_falls_back_to_memory_and_still_limits():
    lim = FakeRedis(hourly=2, daily=100)
    lim.fail = True
    lim.check("a"); lim.check("a")
    with pytest.raises(LimitExceeded):
        lim.check("a")
    assert lim.status().startswith("memory")


def test_status_is_shared_only_when_the_store_answers():
    lim = FakeRedis()
    assert lim.status() == "shared"
    lim.fail = True
    assert "unreachable" in lim.status()
    assert Limiter().status().startswith("memory (shared store not configured")

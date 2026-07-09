"""
Simple Redis-backed counters, incremented by the worker and read by the
API's /metrics route. Counters live in Redis (not in-process) specifically
because the worker runs as multiple replicas — an in-process counter would
only ever reflect one replica's activity, not the fleet's.
"""
from jobstate import get_redis

COUNTER_PREFIX = "guardrail:metrics:"


def incr(name: str, amount: int = 1) -> None:
    r = get_redis()
    r.incrby(f"{COUNTER_PREFIX}{name}", amount)


def get(name: str) -> int:
    r = get_redis()
    val = r.get(f"{COUNTER_PREFIX}{name}")
    return int(val) if val else 0

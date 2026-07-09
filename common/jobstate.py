"""
Scan job status is stored as a Redis hash so both the API (writer/reader)
and the worker (writer) can share state without a database in Phase 1.
Phase 3: this becomes rows in Postgres, updated via the same job_id key.
"""
import json
import os

import redis

_redis_client = None


def get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            os.environ.get("REDIS_URL", "redis://redis:6379/0")
        )
    return _redis_client


def set_job(job_id: str, **fields):
    r = get_redis()
    r.set(f"job:{job_id}", json.dumps(fields), ex=60 * 60 * 24)  # 24h TTL


def update_job(job_id: str, **fields):
    r = get_redis()
    existing = get_job(job_id) or {}
    existing.update(fields)
    r.set(f"job:{job_id}", json.dumps(existing), ex=60 * 60 * 24)


def get_job(job_id: str) -> dict | None:
    r = get_redis()
    raw = r.get(f"job:{job_id}")
    return json.loads(raw) if raw else None

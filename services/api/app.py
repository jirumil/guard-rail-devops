import os
import sys
import uuid
from pathlib import Path

from flask import Flask, Response, request, jsonify
from flask_cors import CORS
from prometheus_client import CollectorRegistry, Gauge, generate_latest, CONTENT_TYPE_LATEST
from redis import Redis
from rq import Queue

sys.path.append("/app/common")
from jobstate import set_job, get_job  # noqa: E402
from logutil import configure_logging  # noqa: E402
import metrics  # noqa: E402

logger = configure_logging("guardrail-api")

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/app/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# GuardRail ingests ANY file type by design — pre-filtering by MIME type
# would defeat the point of a scanning pipeline. We only cap size, to
# protect the API's own request-handling resources.
MAX_BYTES = 100 * 1024 * 1024  # 100MB

# Set by --build-arg GIT_SHA in the Dockerfile, baked into the image at
# build time via ENV. This is what lets you positively verify which
# commit is actually running in a given revision — curl /healthz instead
# of guessing whether a redeploy actually shipped new code.
GIT_SHA = os.environ.get("GIT_SHA", "unknown")

app = Flask(__name__)
CORS(app)  # relax in Phase 1 only; restrict to the real frontend origin in Phase 3

# Lazy singletons, not module-level connections. This is the same pattern
# jobstate.py already uses for Redis, applied consistently here so the
# whole module can be imported — and its routes exercised with Flask's
# test client — without a live Redis server. Tests monkeypatch these two
# functions directly rather than needing a real connection.
_redis_conn = None
_queue = None


def get_redis_conn():
    global _redis_conn
    if _redis_conn is None:
        _redis_conn = Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
    return _redis_conn


def get_queue():
    global _queue
    if _queue is None:
        _queue = Queue("file-scanning", connection=get_redis_conn())
    return _queue


@app.get("/healthz")
def healthz():
    try:
        get_redis_conn().ping()
    except Exception as exc:
        logger.warning("healthz degraded: redis unreachable (%s)", exc)
        return jsonify(status="degraded", redis="unreachable", git_sha=GIT_SHA), 503
    return jsonify(status="ok", git_sha=GIT_SHA), 200


@app.get("/metrics")
def prometheus_metrics():
    """Prometheus text-exposition endpoint. Queue depth and registry sizes
    are read live from RQ; scan outcome counts are read from the Redis
    counters the worker fleet increments. This is the direct observability
    seam Phase 4's Log Analytics / Grafana dashboards plug into."""
    registry = CollectorRegistry()
    q = get_queue()

    Gauge("guardrail_queue_depth", "Jobs waiting to be picked up by a worker", registry=registry).set(len(q))
    Gauge("guardrail_queue_started", "Jobs currently being processed by a worker", registry=registry).set(len(q.started_job_registry))
    Gauge("guardrail_queue_failed", "Jobs that raised an exception (dead-letter visibility)", registry=registry).set(len(q.failed_job_registry))
    Gauge("guardrail_queue_finished", "Jobs completed since the queue was created", registry=registry).set(len(q.finished_job_registry))

    counter_metrics = {
        "guardrail_scans_total": "scans_total",
        "guardrail_scans_clean_total": "scans_clean_total",
        "guardrail_scans_quarantined_total": "scans_quarantined_total",
        "guardrail_scans_failed_total": "scans_failed_total",
        "guardrail_findings_trojan_total": "findings_trojan_total",
        "guardrail_findings_malware_total": "findings_malware_total",
        "guardrail_findings_spyware_total": "findings_spyware_total",
    }
    for metric_name, redis_key in counter_metrics.items():
        Gauge(metric_name, f"GuardRail counter: {redis_key}", registry=registry).set(metrics.get(redis_key))

    return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)


@app.post("/ingest")
def ingest():
    """Accepts any file, stores it, and enqueues a scan task. This route
    does almost no work itself — inspecting *content* is the worker's job.
    The API's only responsibility is: accept fast, store safely, hand off,
    respond — so its latency never depends on scan complexity or backlog.
    """
    if "file" not in request.files:
        logger.warning("ingest rejected: no file part in request")
        return jsonify(error="no file part"), 400

    file = request.files["file"]
    if file.filename == "":
        logger.warning("ingest rejected: empty filename")
        return jsonify(error="empty filename"), 400

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_BYTES:
        logger.warning("ingest rejected: %s exceeds size limit (%d bytes)", file.filename, size)
        return jsonify(error="file exceeds 100MB limit"), 413

    job_id = str(uuid.uuid4())
    original_name = Path(file.filename).name  # strip any path components
    ext = Path(original_name).suffix or ""
    saved_path = UPLOAD_DIR / f"{job_id}{ext}"
    file.save(saved_path)

    set_job(
        job_id,
        status="queued",
        progress=20,
        detail="Ingested — queued for security scan",
        filename=original_name,
        size_bytes=size,
        content_type=file.content_type or "application/octet-stream",
        verdict=None,
        summary=None,
        findings=[],
        url=None,
    )

    # Enqueue is the seam that becomes an Azure Storage Queue / Service Bus
    # publish in Phase 3 — the worker side barely changes.
    get_queue().enqueue(
        "worker.scan_file",
        job_id,
        str(saved_path),
        ext,
        file.content_type or "application/octet-stream",
        original_name,
        job_timeout=120,
    )

    logger.info("ingested job_id=%s filename=%s size_bytes=%d", job_id, original_name, size)

    return jsonify(job_id=job_id, filename=original_name, status="queued"), 202


@app.get("/status/<job_id>")
def status(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify(error="job not found"), 404
    return jsonify(job), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

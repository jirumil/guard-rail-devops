import os
import sys
import time

sys.path.append("/app/common")
from jobstate import update_job  # noqa: E402
from storage import get_storage  # noqa: E402
from logutil import configure_logging  # noqa: E402
import metrics  # noqa: E402

logger = configure_logging("guardrail-worker")

# Storage is created lazily, not at import time. Two reasons: (1) it makes
# this module importable in unit tests without a live MinIO connection,
# and (2) it matches the same lazy-connection pattern jobstate.py already
# uses for Redis — one consistent rule for the whole codebase: no network
# I/O as a side effect of `import`.
_storage = None


def _get_storage_client():
    global _storage
    if _storage is None:
        _storage = get_storage()
    return _storage

# --- Threat pattern heuristics ------------------------------------------
# SIMULATED detection for portfolio/demo purposes — pattern matching, not a
# real antivirus engine. In production this stage would call something
# like ClamAV, a sandboxed detonation service, or a vendor scanning API.
# The transferable engineering lesson is the async, isolated architecture
# around this function — not the detection logic itself, which is kept
# simple and legible on purpose.
#
# Each rule maps to one of three threat categories so the frontend can
# render an itemized breakdown rather than a single pass/fail flag —
# mirroring how real EDR/AV tooling classifies findings by threat family.

TROJAN_EXTENSIONS = {".exe", ".scr", ".msi", ".bat", ".cmd"}
SPYWARE_EXTENSIONS = {".vbs", ".ps1", ".dll", ".jar"}

TROJAN_PATTERNS = [
    "powershell -enc",
    "certutil -decode",
    "/bin/sh -c",
    "reverse_tcp",
]
MALWARE_PATTERNS = [
    "eval(",
    "base64_decode",
    "exec(",
    "rm -rf",
    "drop table",
    "wget http",
    "curl http",
]
SPYWARE_PATTERNS = [
    "sudo ",
    "keylogger",
    "clipboard.read",
    "webcam",
    "getenv(",
]

# Only text-scan file types where reading as text is meaningful — scanning
# arbitrary binary content as UTF-8 text produces noisy false positives.
TEXT_SCAN_EXTENSIONS = {".txt", ".py", ".js", ".sh", ".php", ".json", ".yml", ".yaml", ".xml", ".html"}
MAX_SCAN_BYTES = 2 * 1024 * 1024  # bound the read so a huge text file can't stall a worker


def scan_file(job_id: str, local_path: str, ext: str, content_type: str, original_name: str):
    """RQ entrypoint. Runs in the worker container, isolated from the API's
    request/response cycle — the API's latency never depends on how long
    this function takes or how deep the queue backlog is."""
    try:
        logger.info("scan started job_id=%s filename=%s", job_id, original_name)
        update_job(job_id, status="scanning", progress=50, detail="Running heuristic threat scan")
        time.sleep(1.2)  # simulate meaningful scan work

        findings = _run_heuristics(ext.lower(), local_path)
        counts = _tally(findings)
        verdict = "quarantined" if findings else "clean"
        summary = (
            f"Scan Complete: {counts['trojan']} Trojan, "
            f"{counts['malware']} Malware, {counts['spyware']} Spyware "
            f"patterns identified"
        )

        update_job(job_id, status="uploading", progress=80, detail="Archiving to secure sandbox")
        key = f"{job_id}{ext}"
        storage = _get_storage_client()
        url = storage.upload(key=key, local_path=local_path, content_type=content_type)

        update_job(
            job_id,
            status="success",
            progress=100,
            detail=summary,
            verdict=verdict,
            summary=summary,
            findings=findings,
            url=url,
        )

        # Compliance footer claims immediate deletion post-analysis — make
        # that literally true in both places the file exists: the object
        # store copy AND the shared uploads volume. Deleting only the MinIO
        # copy (the original oversight here) leaves the raw file sitting on
        # disk indefinitely — a real gap, now closed.
        storage.delete(key)
        _cleanup_local_file(local_path)

        metrics.incr("scans_total")
        metrics.incr("scans_clean_total" if verdict == "clean" else "scans_quarantined_total")
        for category, count in counts.items():
            if count:
                metrics.incr(f"findings_{category}_total", count)

        logger.info("scan complete job_id=%s verdict=%s findings=%d", job_id, verdict, len(findings))

    except Exception as exc:  # noqa: BLE001
        logger.error("scan failed job_id=%s error=%s", job_id, exc)
        update_job(job_id, status="error", detail=str(exc), verdict="error", summary="Scan failed")
        metrics.incr("scans_failed_total")
        _cleanup_local_file(local_path)


def _cleanup_local_file(local_path: str) -> None:
    """Best-effort removal of the shared-volume copy. Failure to delete
    is logged implicitly via the exception being swallowed — a missing
    temp file is not worth failing a scan job over, but leaving one
    behind forever (the original bug) is worth actively preventing."""
    try:
        if os.path.exists(local_path):
            os.remove(local_path)
    except OSError:
        pass


def _run_heuristics(ext: str, local_path: str) -> list[dict]:
    """Returns a list of structured findings, each tagged with a threat
    category, so the frontend can render an itemized breakdown."""
    findings = []

    if ext in TROJAN_EXTENSIONS:
        findings.append({
            "category": "trojan",
            "detail": f"Executable/dropper extension flagged: {ext}",
        })
    if ext in SPYWARE_EXTENSIONS:
        findings.append({
            "category": "spyware",
            "detail": f"Scripting/monitoring-capable extension flagged: {ext}",
        })

    if ext in TEXT_SCAN_EXTENSIONS:
        findings.extend(_scan_text_content(local_path))

    return findings


def _scan_text_content(local_path: str) -> list[dict]:
    findings = []
    try:
        with open(local_path, "r", errors="ignore") as f:
            content = f.read(MAX_SCAN_BYTES).lower()
    except Exception:
        return [{"category": "spyware", "detail": "Content unreadable — flagged for manual review"}]

    for pattern in TROJAN_PATTERNS:
        if pattern in content:
            findings.append({"category": "trojan", "detail": f"Trojan-pattern match: '{pattern.strip()}'"})
    for pattern in MALWARE_PATTERNS:
        if pattern in content:
            findings.append({"category": "malware", "detail": f"Malware-pattern match: '{pattern.strip()}'"})
    for pattern in SPYWARE_PATTERNS:
        if pattern in content:
            findings.append({"category": "spyware", "detail": f"Spyware-pattern match: '{pattern.strip()}'"})

    return findings


def _tally(findings: list[dict]) -> dict:
    counts = {"trojan": 0, "malware": 0, "spyware": 0}
    for f in findings:
        cat = f.get("category")
        if cat in counts:
            counts[cat] += 1
    return counts

# GuardRail

**Asynchronous file ingestion & threat-scanning pipeline**, built as a decoupled, horizontally-scalable microservice architecture — designed to demonstrate production-grade resilience patterns for high-throughput enterprise file intake.

---

## Executive Summary

GuardRail is a portfolio implementation of a pattern used across enterprise security tooling: **untrusted files arrive faster than they can be safely inspected, so ingestion and inspection must be decoupled.**

Rather than scanning files synchronously inside the request/response cycle — a design that collapses under load — GuardRail accepts files fast, hands them to an isolated worker fleet for inspection, and reports scan verdicts back to the client asynchronously. The result is a system that behaves the same under 1 concurrent upload or 1,000: predictable latency, no dropped requests, no server crashes.

This project simulates the scanning logic itself (pattern-matching against forbidden extensions and known-suspicious strings) rather than integrating a production antivirus engine — the architecture is the deliverable, not the detection algorithm. Swapping in a real engine (ClamAV, a sandboxed detonation service, VirusTotal's API) requires touching exactly one function; the ingestion, queueing, and status-reporting layers don't change.

---

## Architecture

```
                  ┌──────────────┐
  Browser ───────▶│  Flask API   │──── stores raw file ────▶  MinIO (quarantine bucket)
  (drag & drop)   │  /ingest     │
                  └──────┬───────┘
                         │ enqueue scan task (metadata only)
                         ▼
                  ┌──────────────┐
                  │    Redis     │◀─── job status read/write
                  │  (job queue  │
                  │  + job state)│
                  └──────┬───────┘
                         │ dequeue
                         ▼
                  ┌──────────────┐
                  │   Worker(s)  │──── scan (pattern match) ──▶ verdict: clean / quarantined
                  │  (N replicas)│
                  └──────────────┘
```

| Layer | Responsibility |
|---|---|
| **Flask API** | Accept any file type, validate size only, persist to disk, enqueue a scan task, return immediately (202 Accepted) |
| **Redis** | Durable queue (via RQ) + shared job-state store, polled by the frontend for live status |
| **Worker (N replicas)** | Dequeue tasks one at a time, run the scan, upload the file to quarantine storage, write the verdict |
| **MinIO** | S3-compatible object storage, standing in for Azure Blob Storage — files land in a private quarantine bucket, not a public one |
| **Frontend** | Static dashboard; polls `/status/<job_id>` and renders live pipeline state without a page reload |

---

## The 1,000-Upload Resilience Strategy

The core engineering claim of this project is narrow and specific: **the Flask API never performs scan work, and therefore its response time is decoupled from scan complexity, scan backlog, and worker capacity.**

Here's why that matters under load, concretely:

**Without a queue** (naïve synchronous design): each incoming request would hold open an API worker thread/process for the full duration of the scan. Gunicorn (or any WSGI server) runs a fixed pool of worker processes — commonly 2–4 per CPU core. If 1,000 files arrive in a burst and each scan takes even 1–2 seconds, the API's entire worker pool is saturated almost immediately. Requests 5 through 1,000 queue up *at the TCP/socket level*, waiting for a free process — and many will simply time out from the client's perspective, or the server's memory footprint balloons as it tries to hold open hundreds of simultaneous file uploads in-process.

**With GuardRail's design:** the `/ingest` endpoint does three fast, bounded operations — read the file to disk, write a small JSON record to Redis, push a job reference onto a queue — and returns. None of these steps scale with scan complexity. A 1,000-file burst produces 1,000 fast `202 Accepted` responses; the API's memory and thread usage stay flat regardless of how much scanning work is backed up behind it.

**Redis acts as the shock absorber.** The queue holds the backlog — not the API process, not open HTTP connections. A sudden traffic spike becomes a longer queue depth, not a wave of failed or hung requests. This is the same pattern that lets a coffee shop take 50 orders in the first minute of a rush without 50 baristas standing idle the rest of the day — the order queue absorbs the burst; the (fixed-size) kitchen staff works through it at a sustainable pace.

**The worker fleet is the only thing that scales with scan volume, and it's isolated.** Because workers are separate containers/processes consuming from the same queue, adding capacity is just adding replicas (`deploy.replicas: N` locally; KEDA-driven autoscaling on queue depth in the Azure Container Apps target architecture) — with zero changes to the API or frontend. If a scan hangs, crashes, or runs slow, it degrades *worker throughput*, never *API availability*. The blast radius of a bad file is contained to a single worker process, not the whole system.

In short: **the queue converts a traffic spike (an availability problem) into a queue-depth metric (a capacity-planning problem)** — and capacity-planning problems are solvable by scaling workers, without ever touching the client-facing API.

---

## Project Structure

```
pixelvault/
├── docker-compose.yml
├── .env.example
├── common/
│   ├── jobstate.py        # shared Redis job-state read/write
│   └── storage.py         # storage abstraction (MinIO now, Azure Blob later)
└── services/
    ├── frontend/           # nginx + static dashboard (polls job status)
    ├── api/                # Flask — /ingest, /status/<id>, /healthz
    └── worker/             # RQ worker — scan_file(), pattern-based detection
```

*(Directory name retained from an earlier project iteration — the layout maps 1:1 to the architecture above regardless of folder naming.)*

---

## Quickstart

**Prerequisites:** Docker + Docker Compose, running locally (tested on WSL2/Linux).

```bash
git clone <your-repo-url>
cd pixelvault
cp .env.example .env

docker compose up --build
```

Once all services report healthy:

```bash
docker compose ps
```

Open the dashboard:

```
http://localhost:8080
```

Drag any file into the dropzone and watch it move through **Queued → Scanning → Archiving → Complete**, with a **Clean** or **Quarantined** verdict pill on completion.

**Try triggering a detection** — create a text file containing one of the flagged patterns and upload it:
```bash
echo 'eval(user_input)' > test-suspicious.txt
```
This should return a **Quarantined** verdict with a listed finding, demonstrating the scan logic end-to-end.

**Inspect stored files directly** via the MinIO console:
```
http://localhost:9001
```
Login: `minioadmin` / `minioadmin` — browse the `guardrail-quarantine` bucket.

**Tear down:**
```bash
docker compose down -v
```

---

## Roadmap (Phases 3–4)

- **Phase 3:** Terraform-provisioned Azure Container Apps deployment — API and worker as independently-scaling Container Apps, worker autoscaling on Redis queue depth via KEDA, storage migrated to Azure Blob Storage behind the same `ObjectStorage` interface.
- **Phase 4:** GitHub Actions CI/CD (build → push to ACR → `terraform apply`), Azure Monitor/Log Analytics for scan-throughput and quarantine-rate observability.

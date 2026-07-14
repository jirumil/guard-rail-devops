# GuardRail

**An asynchronous, auto-scaling file ingestion and threat-scanning pipeline — built to demonstrate production-grade cloud architecture, not just a working demo.**

GuardRail accepts untrusted file uploads, queues them for inspection, and scans them for known threat patterns (Trojan/Malware/Spyware signatures) — all without ever blocking the client on scan latency. The system is designed around a single principle: **ingestion and inspection are decoupled**, so the pipeline behaves identically whether it's handling 1 upload or 1,000.

---

## Core Features

**Application**
- **API** — a thin, fast Flask service that validates uploads, writes them to object storage, and enqueues a scan job. Never performs scanning itself, so its latency never depends on scan backlog.
- **Worker** — a horizontally-scalable fleet that pulls jobs from a Redis queue, downloads the file from object storage, runs heuristic threat detection, and reports a structured, itemized verdict (Trojan / Malware / Spyware counts, not just pass/fail).
- **Frontend** — a real-time dashboard that polls scan status and renders live pipeline state (Queued → Scanning → Archiving → Complete) with no page reload.

**Infrastructure**
- **Terraform** — full infrastructure-as-code for Azure Container Apps, Azure Blob Storage, Azure Container Registry, and Redis, including KEDA-based autoscaling rules.
- **Docker Compose** — a complete local development environment (API, worker, frontend, Redis, MinIO) that mirrors the cloud topology exactly.
- **GitHub Actions CI/CD** — automated test gate → build → push → deploy pipeline; a failing test suite blocks the deploy from ever reaching the registry.
- **Pre-commit hooks** — Black, Flake8, and a custom static-analysis check that catches invisible Unicode whitespace characters before they reach a commit.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| API framework | Flask + Gunicorn |
| Async task queue | Redis + Python-RQ |
| Object storage | Azure Blob Storage (cloud) / MinIO (local, S3-compatible) |
| Frontend | Vanilla JS + Tailwind CSS |
| Containerization | Docker, multi-stage builds |
| Local orchestration | Docker Compose |
| Cloud infrastructure | Terraform (HCL), Azure Container Apps |
| Autoscaling | KEDA (scale-to-zero on idle, burst on queue depth) |
| CI/CD | GitHub Actions |
| Testing | Pytest, fakeredis (28 automated tests, zero live infrastructure required) |
| Observability | Structured JSON logging to stdout, Prometheus-format `/metrics` endpoint |

---

## Architecture Overview

```
Browser ──▶ API (Flask) ──▶ uploads to Blob Storage
                │
                └─▶ enqueues job in Redis
                                │
                                ▼
                    Worker fleet (0–10 replicas, KEDA-scaled)
                                │
                    downloads from Blob Storage → scans → verdict
                                │
                    updates job status in Redis ◀── polled by frontend
```

The API and worker never share a filesystem or make assumptions about each other's local disk — every file transfer between them happens through the object storage layer. This means either side can scale, restart, or run across separate machines without coordination. The worker scales to **zero replicas when idle** (protecting infrastructure cost) and bursts up automatically as queue depth grows, via a KEDA scale rule watching the Redis job queue.

---

## How to Run Locally

**Prerequisites:** Docker and Docker Compose.

```bash
git clone <this-repo-url>
cd guardrail
cp .env.example .env
docker compose up --build -d
```

Once all services report healthy:
```bash
docker compose ps
```

Open the dashboard:
```
http://localhost:8080
```

Drop any file into the dropzone and watch it move through the full pipeline in real time.

**Run the test suite:**
```bash
make test
```

**Tear down:**
```bash
docker compose down -v
```

---

## Cloud Deployment

Full Terraform configuration for Azure Container Apps lives in `infra/terraform/`. See that directory for the provisioning workflow, or `scripts/build.sh` for the image build/tag/push pipeline that mirrors what CI runs automatically on every push to `master`.

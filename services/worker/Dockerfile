# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

FROM base AS deps
COPY services/worker/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN useradd --create-home --uid 1000 appuser
COPY --from=deps /root/.local /home/appuser/.local
COPY common/ /app/common/
COPY services/worker/worker.py .
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1
USER appuser
CMD ["python", "worker.py"]

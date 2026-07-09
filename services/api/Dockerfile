# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

FROM base AS deps
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim AS runtime
WORKDIR /app
ARG GIT_SHA=unknown
LABEL org.opencontainers.image.revision=$GIT_SHA
RUN useradd --create-home --uid 1000 appuser
COPY --from=deps /root/.local /home/appuser/.local
COPY common/ /app/common/
COPY services/api/app.py .
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    GIT_SHA=$GIT_SHA
RUN mkdir -p /app/uploads && chown -R appuser:appuser /app
USER appuser
EXPOSE 5000
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/healthz')" || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60", "app:app"]

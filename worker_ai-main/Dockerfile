FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /service

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1001 worker

COPY --from=builder /install /usr/local

COPY . .
RUN mkdir -p /service/data && chown -R worker:worker /service

USER worker

EXPOSE 8100

HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8100/healthz || exit 1

CMD ["python", "worker.py"]

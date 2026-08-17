# Steward's backend on Cloud Run.
#
# Slim rather than alpine: several of the Google client libraries ship manylinux
# wheels that musl can't use, and building them from source would cost minutes
# per deploy for no benefit.
FROM python:3.11-slim

# Bytecode written at build time, not on every cold start; unbuffered so logs
# reach Cloud Logging as they happen rather than when a buffer fills.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Requirements first, so a code-only change reuses the dependency layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run sends traffic to $PORT and it is not always 8080. One worker: this
# is IO-bound on Firestore and Vertex, and concurrency is what Cloud Run's own
# request handling is for.
ENV PORT=8080
CMD exec uvicorn api:app --host 0.0.0.0 --port ${PORT}

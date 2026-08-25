# RAPTOR Agentic Observatory — API Dockerfile
# Tek bağımsız, non-root, read-only, minimal image.
# Hermes'in node'u veya runtime'ına bağımlı DEĞİLDİR.

ARG PYTHON_IMAGE

FROM ${PYTHON_IMAGE}

# non-root kullanıcı (10001:10001)
RUN groupadd -g 10001 raptor && useradd -u 10001 -g raptor -s /usr/sbin/nologin raptor

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Sistem bağımlılıkları (psycopg binary, build) — pinned değil ama minimal
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/raptor

# Önce bağımlılıklar (cache layer)
COPY packages/requirements-api.txt /srv/raptor/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama
COPY packages/ packages/
COPY apps/api/ apps/api/
COPY migrations/ migrations/

USER raptor
EXPOSE 8000
# Uvicorn: tek worker, localhost içi (gateway önünde)
CMD ["sh", "-c", "alembic -c migrations/alembic.ini upgrade head && uvicorn apps.api.app:app --host 0.0.0.0 --port 8000 --workers 1"]
FROM python:3.12-slim@sha256:7a8b475003c4fe15a2cd4e55e5cfc2f3560bdc9333d624f24cdd6d4340fd7a17

RUN groupadd -g 10001 raptor && useradd -u 10001 -g raptor -s /usr/sbin/nologin raptor
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/raptor
# packages/ içeriğini köke kopyala => from observability, agent_core, policy vs top-level
COPY packages/requirements-worker.txt /srv/raptor/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY packages/ /srv/raptor/
COPY apps/worker/ /srv/raptor/apps/worker/
USER raptor
EXPOSE 8001
CMD ["uvicorn", "apps.worker.worker:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
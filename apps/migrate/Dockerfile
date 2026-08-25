# RAPTOR — one-shot migration servisi (API migration çalıştırmaz; web build yok)
ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}

RUN groupadd -g 10001 raptor && useradd -u 10001 -g raptor -s /usr/sbin/nologin raptor

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/raptor

COPY packages/requirements-api.txt /srv/raptor/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY packages/ /srv/raptor/
COPY migrations/ migrations/

USER raptor
CMD ["sh", "-c", "alembic -c migrations/alembic.ini upgrade head"]

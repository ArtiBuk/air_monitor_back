FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ARG TORCH_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl procps tini \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY apps /app/apps
COPY config /app/config
COPY manage.py /app/manage.py
COPY docker /opt/docker

RUN pip install --upgrade pip setuptools wheel \
    && pip install --extra-index-url "${TORCH_EXTRA_INDEX_URL}" -e . \
    && chmod +x /opt/docker/app/entrypoints/*.sh /opt/docker/app/healthcheck/*.sh

ENTRYPOINT ["/usr/bin/tini", "--"]

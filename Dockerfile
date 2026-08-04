# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN apt-get update \
  && apt-get upgrade -y \
  && apt-get install -y --no-install-recommends build-essential ffmpeg python3-dev wget \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

ARG UID=1000
ARG GID=1000
RUN addgroup --gid ${GID} python \
  && adduser --disabled-password --gecos "" --home /app --uid ${UID} --gid ${GID} python \
  && chown -R python:python /app

COPY --chown=python:python pyproject.toml README.md /app/
# Install dependencies without installing a placeholder copy of outgram. A
# placeholder package makes the console script point to stale source when the
# final project installation has the same version.
RUN --mount=type=cache,target=/root/.cache/pip \
  pip install --cache-dir /root/.cache/pip --upgrade pip \
  && pip install --cache-dir /root/.cache/pip --group img

ARG ENV_TYPE=production
ENV ENV_TYPE=${ENV_TYPE}
RUN if [ "$(echo "$ENV_TYPE" | tr '[:upper:]' '[:lower:]')" != "production" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends git make \
      && pip install --cache-dir /root/.cache/pip --group dev \
      && apt-get clean \
      && rm -rf /var/lib/apt/lists/*; \
    fi

COPY --chown=python:python . /app/
RUN --mount=type=cache,target=/root/.cache/pip \
  pip install --cache-dir /root/.cache/pip --no-deps .
USER python

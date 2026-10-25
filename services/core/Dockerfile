FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

RUN groupadd --gid 10001 gmmedia \
    && useradd --uid 10001 --gid gmmedia --create-home --shell /usr/sbin/nologin gmmedia

COPY --chown=gmmedia:gmmedia app ./app
COPY --chown=gmmedia:gmmedia migrations ./migrations

USER gmmedia
EXPOSE 8000

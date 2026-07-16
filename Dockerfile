FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARCHIVE_HOST=0.0.0.0 \
    ARCHIVE_PORT=8080 \
    ARCHIVE_DATA_DIR=/data \
    ARCHIVE_ROOT=/archive

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 archive \
    && useradd --uid 10001 --gid archive --create-home --shell /usr/sbin/nologin archive

WORKDIR /app

COPY --chown=archive:archive app/ /app/app/

RUN mkdir -p /data /archive \
    && chmod 700 /data /archive \
    && chmod -R a+rX /app/app \
    && chown -R archive:archive /data /archive /app

USER archive

EXPOSE 8080

VOLUME ["/data", "/archive"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('ARCHIVE_PORT','8080')+'/healthz', timeout=3).read()"]

ENTRYPOINT ["python", "-m", "app"]

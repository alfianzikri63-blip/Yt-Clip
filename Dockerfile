FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates gosu && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-ai.txt ./
# Full server-side AI speech: install with the rest of the app.
RUN pip install --no-cache-dir -r requirements-ai.txt
COPY app.py smart_clip.py ./
COPY static ./static
RUN mkdir -p /app/data && useradd -r -u 10001 clipforge && chown -R clipforge:clipforge /app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENV CLIPFORGE_PUBLIC=1 CLIPFORGE_DATA_DIR=/app/data CLIPFORGE_WHISPER_MODEL=tiny PORT=10000
EXPOSE 10000
CMD ["/usr/local/bin/docker-entrypoint.sh"]

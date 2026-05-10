# Tiny container for the yt-dlp sidecar.
# Python slim base + ffmpeg (some YT formats need remuxing) + yt-dlp.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ffmpeg is needed for yt-dlp to remux AAC / opus into containers
# the browser can decode; ca-certificates so HTTPS to YouTube works.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp pinned to a recent release. Bump periodically — YouTube
# breaks extractors every few weeks.
RUN pip install --no-cache-dir 'yt-dlp>=2025.1.26'

WORKDIR /app
COPY app.py /app/app.py

EXPOSE 8080

CMD ["python", "app.py"]

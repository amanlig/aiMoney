FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# OCR remains local, with the same manual-entry fallback as the desktop app.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY profile_settings.js ./
COPY frontend/ ./frontend/
COPY docs/ ./docs/
COPY models/ ./models/
RUN python frontend/build.py \
    && useradd --create-home --uid 1000 app \
    && mkdir -p data reports .secrets \
    && chmod -R a+rX /app \
    && chown -R app:app /app
USER app
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8765/api/health', timeout=3).close()"
# One worker preserves the broker-token and refresh locks in this local app.
CMD ["uvicorn", "dashboard_server:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1", "--no-proxy-headers"]

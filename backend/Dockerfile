FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng libglib2.0-0 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && python -m spacy download en_core_web_sm

COPY app ./app
RUN useradd --system --uid 10001 afterimage && mkdir -p /data/storage && chown -R afterimage /data
USER afterimage

ENV AFTERIMAGE_STORAGE_DIR=/data/storage AFTERIMAGE_ENV=production
EXPOSE 8000
# Hosts like Render set $PORT; default to 8000 otherwise.
CMD ["sh", "-c", "exec uvicorn app.main:app_factory --factory --host 0.0.0.0 --port ${PORT:-8000} --no-access-log --proxy-headers --forwarded-allow-ips='*'"]

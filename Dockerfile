FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARGOS_CHUNK_TYPE=MINISBD \
    ARGOS_DEVICE_TYPE=cpu \
    ARGOS_COMPUTE_TYPE=int8

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps argostranslate==1.11.0

COPY backend/app ./app
COPY index.html ./index.html

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

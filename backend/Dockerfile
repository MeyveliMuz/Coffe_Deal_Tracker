# Coffee Deal Tracker — backend (FastAPI + Playwright)
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Önce bağımlılıklar — katman cache'i için
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Playwright Chromium + OS bağımlılıkları
RUN playwright install --with-deps chromium

# Paylaşılan çekirdek + backend + config
COPY src ./src
COPY backend ./backend
COPY config.json ./config.json

# Fiyat geçmişi DB'si burada oluşur (compose'da volume ile kalıcı)
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

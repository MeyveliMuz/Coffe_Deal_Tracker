"""FastAPI uygulaması ve REST/WebSocket rotaları.

Çalıştırma (proje kökünden):
    py -3.14 -m uvicorn backend.main:app --reload --port 8000
Swagger UI: http://localhost:8000/docs
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# `src` paketini import edebilmek için proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import AppConfig

from . import scheduler, services
from .scan_manager import manager
from .schemas import (
    AlertIn,
    AlertOut,
    ConfigModel,
    DealOut,
    HistoryPoint,
    ProductOut,
    ScanStatus,
    deal_to_dict,
    product_to_dict,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Açılışta zamanlayıcıyı başlat (config'e göre günlük tarama kurar)
    scheduler.start_scheduler()
    yield
    scheduler.stop_scheduler()


app = FastAPI(
    title="Coffee Deal Tracker API",
    version="0.1.0",
    description="Masaüstü uygulamasıyla aynı çekirdeği paylaşan web backend'i.",
    lifespan=lifespan,
)

# Geliştirme için CORS — Vite (5173) ve CRA (3000) origin'leri + yerel
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config", response_model=ConfigModel)
def get_config() -> dict:
    return services.load_config().to_dict()


@app.put("/api/config", response_model=ConfigModel)
def put_config(cfg: ConfigModel) -> dict:
    new_cfg = AppConfig(
        brands=[b.strip().lower() for b in cfg.brands],
        sites=[s.strip().lower() for s in cfg.sites],
        history_days=cfg.history_days,
        max_products_per_brand_per_site=cfg.max_products_per_brand_per_site,
        request_delay_ms=cfg.request_delay_ms,
        headless=cfg.headless,
        search_suffix=cfg.search_suffix,
        product_types=[t.strip().lower() for t in cfg.product_types] or ["cekirdek"],
        start_with_windows=cfg.start_with_windows,
        auto_scan_on_launch=cfg.auto_scan_on_launch,
        schedule_enabled=cfg.schedule_enabled,
        schedule_time=cfg.schedule_time,
    )
    services.save_config(new_cfg)
    scheduler.reschedule(new_cfg)  # zamanlama değiştiyse job'u güncelle
    return new_cfg.to_dict()


@app.get("/api/products", response_model=list[ProductOut])
def get_products() -> list[dict]:
    products, _ = services.snapshot(services.load_config())
    return [product_to_dict(p) for p in products]


@app.get("/api/deals", response_model=list[DealOut])
def get_deals() -> list[dict]:
    _, deals = services.snapshot(services.load_config())
    return [deal_to_dict(d) for d in deals]


@app.get("/api/history", response_model=list[HistoryPoint])
def get_history(url: str, window_days: int = 90) -> list[dict]:
    points = services.price_history(url, window_days=window_days)
    return [{"t": t, "price": p} for t, p in points]


@app.get("/api/alerts", response_model=list[AlertOut])
def get_alerts() -> list[dict]:
    return services.list_alerts()


@app.post("/api/alerts", response_model=AlertOut, status_code=201)
def create_alert(alert: AlertIn) -> dict:
    if alert.target_price <= 0:
        raise HTTPException(status_code=400, detail="Hedef fiyat 0'dan büyük olmalı")
    return services.add_alert(alert.url, alert.target_price)


@app.delete("/api/alerts/{alert_id}", status_code=204)
def remove_alert(alert_id: int) -> None:
    services.delete_alert(alert_id)


@app.get("/api/schedule")
def schedule_info() -> dict:
    cfg = services.load_config()
    return {
        "enabled": cfg.schedule_enabled,
        "time": cfg.schedule_time,
        "next_run": scheduler.next_run(),
    }


@app.get("/api/scan", response_model=ScanStatus)
def scan_status() -> dict:
    return manager.status_dict()


@app.post("/api/scan", response_model=ScanStatus, status_code=202)
async def start_scan() -> dict:
    # async def: event loop üzerinde çalışır, böylece manager.start() içindeki
    # asyncio.create_task çağrıları geçerli bir loop bulur.
    started = manager.start(services.load_config(), services.db_path())
    if not started:
        raise HTTPException(status_code=409, detail="Tarama zaten çalışıyor")
    return manager.status_dict()


@app.post("/api/scan/cancel", response_model=ScanStatus)
async def cancel_scan() -> dict:
    manager.cancel()
    return manager.status_dict()


@app.websocket("/ws/scan")
async def ws_scan(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            # İstemci mesajlarını beklemiyoruz; bağlantıyı canlı tut
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


# Derlenmiş frontend'i sun (varsa). EN SONDA mount edilir; "/api/*", "/ws/scan",
# "/docs" gibi rotalar önce eşleşir. Böylece masaüstü wrapper ve bulut deploy'da
# tek sunucu hem API'yi hem arayüzü verir (http://localhost:8000 → uygulama).
from fastapi.staticfiles import StaticFiles  # noqa: E402

_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
    log.info("Frontend statik dosyaları sunuluyor: %s", _DIST)

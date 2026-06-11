"""Veri erişim servisleri — çekirdek depolama/config katmanını sarar.

API rotaları doğrudan DB/config'e dokunmaz; bu modüldeki fonksiyonları çağırır.
"""
from __future__ import annotations

import logging
from datetime import datetime

from src.core.config import (
    AppConfig,
    default_config_path,
    default_db_path,
    user_config_path,
)
from src.core.deal_detector import detect_deal
from src.core.models import Deal, ProductListing
from src.storage.db import PriceDatabase

log = logging.getLogger(__name__)


def db_path() -> str:
    return str(default_db_path())


def load_config() -> AppConfig:
    return AppConfig.load(default_config_path())


def save_config(cfg: AppConfig) -> None:
    cfg.save(user_config_path())


def snapshot(cfg: AppConfig, hours: int = 48) -> tuple[list[ProductListing], list[Deal]]:
    """Son `hours` saatteki ürün anlık görüntüsü + bunlardan hesaplanan fırsatlar.
    Masaüstü uygulamasının açılışta yaptığı ile aynı mantık."""
    db = PriceDatabase(db_path())
    try:
        rows = db.latest_snapshot(hours=hours)
        products: list[ProductListing] = []
        deals: list[Deal] = []
        for listing, recorded_at in rows:
            products.append(listing)
            deal = detect_deal(
                db, listing, window_days=cfg.history_days, recorded_at=recorded_at
            )
            if deal is not None:
                deals.append(deal)
        return products, deals
    finally:
        db.close()


def price_history(url: str, window_days: int = 90) -> list[tuple[datetime, float]]:
    db = PriceDatabase(db_path())
    try:
        return db.price_history(url, window_days=window_days)
    finally:
        db.close()


# --- fiyat alarmları --------------------------------------------------------
def add_alert(url: str, target_price: float) -> dict:
    db = PriceDatabase(db_path())
    try:
        db.add_alert(url, target_price)
        return next((a for a in db.list_alerts() if a["product_url"] == url), {})
    finally:
        db.close()


def list_alerts() -> list[dict]:
    db = PriceDatabase(db_path())
    try:
        return db.list_alerts()
    finally:
        db.close()


def delete_alert(alert_id: int) -> None:
    db = PriceDatabase(db_path())
    try:
        db.delete_alert(alert_id)
    finally:
        db.close()


def check_alerts() -> list[dict]:
    """Tarama sonrası çağrılır: hedefin altına inen alarmları tetikler."""
    db = PriceDatabase(db_path())
    try:
        return db.check_alerts()
    finally:
        db.close()

"""API istek/yanıt modelleri (Pydantic) + dataclass→dict dönüştürücüler.

Çekirdek dataclass'ları (ProductListing, Deal, ScanSummary) Pydantic değil;
burada onları JSON'a uygun sözlüklere çeviren yardımcılar var. Pydantic
modeller ise Swagger UI dokümantasyonu için.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from src.core.models import Deal, ProductListing, ScanSummary


class ProductOut(BaseModel):
    url: str
    name: str
    brand: str
    site: str
    price: float
    currency: str = "TRY"
    image_url: Optional[str] = None


class DealOut(ProductOut):
    historical_min: Optional[float] = None
    discount_pct: Optional[float] = None
    original_price: Optional[float] = None
    previous_logged_price: Optional[float] = None
    history_points: int = 0


class HistoryPoint(BaseModel):
    t: datetime
    price: float


class ConfigModel(BaseModel):
    brands: list[str]
    sites: list[str]
    history_days: int = 90
    max_products_per_brand_per_site: int = 15
    request_delay_ms: int = 2000
    headless: bool = True
    search_suffix: str = "kahve çekirdeği"
    product_types: list[str] = ["cekirdek"]
    start_with_windows: bool = False
    auto_scan_on_launch: bool = False
    schedule_enabled: bool = False
    schedule_time: str = "09:00"


class AlertIn(BaseModel):
    url: str
    target_price: float


class AlertOut(BaseModel):
    id: int
    product_url: str
    name: Optional[str] = None
    target_price: float
    current_price: Optional[float] = None
    created_at: Optional[str] = None
    triggered_at: Optional[str] = None
    triggered_price: Optional[float] = None


class ScanStatus(BaseModel):
    status: str                      # idle | running | done | error
    running: bool
    last_progress: str = ""
    products_found: int = 0
    deals_found: int = 0
    sites_scanned: int = 0
    errors: list[str] = []
    skipped: list[str] = []
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# ---- dönüştürücüler -------------------------------------------------------
def product_to_dict(l: ProductListing) -> dict:
    return {
        "url": l.url,
        "name": l.name,
        "brand": l.brand,
        "site": l.site,
        "price": l.price,
        "currency": l.currency,
        "image_url": l.image_url,
    }


def deal_to_dict(d: Deal) -> dict:
    base = product_to_dict(d.listing)
    base.update(
        {
            "historical_min": d.historical_min,
            "discount_pct": d.discount_pct,
            "original_price": d.original_price,
            "previous_logged_price": d.previous_logged_price,
            "history_points": d.history_points,
        }
    )
    return base


def summary_to_dict(s: ScanSummary) -> dict:
    return {
        "sites_scanned": s.sites_scanned,
        "brands_scanned": s.brands_scanned,
        "products_found": s.products_found,
        "deals_found": s.deals_found,
        "errors": list(s.errors),
        "skipped": list(s.skipped),
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "finished_at": s.finished_at.isoformat() if s.finished_at else None,
    }

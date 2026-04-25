"""Son N günün en düşük fiyatına göre fırsat tespiti."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from src.core.models import Deal, ProductListing
from src.storage.db import PriceDatabase


def detect_deal(
    db: PriceDatabase,
    listing: ProductListing,
    *,
    window_days: int = 30,
    recorded_at: Optional[datetime] = None,
) -> Optional[Deal]:
    """Bir ürün için fırsat tespiti.

    İki yoldan biriyle fırsat işaretlenir:

    1. Geçmiş bazlı: mevcut fiyat son `window_days` içindeki ÖNCEKİ en
       düşüğün ALTINA indi.
    2. Site bazlı: site kendi listelemesinde üstü çizili eski fiyat
       (`listing.original_price`) gösteriyor ve fark gerçek bir indirim.
       Geçmiş henüz yokken bile (yeni taranmış ürünler) fırsat olarak
       gözükmesini sağlar.

    `recorded_at` verilirse bu tarihten **önceki** kayıtlar kullanılır;
    scanner kendi yeni yazdığı kaydı hariç tutar.
    """
    previous_min = db.previous_min_price(
        listing.url, window_days, before=recorded_at
    )
    previous_points = db.history_count(
        listing.url, window_days, before=recorded_at
    )

    # 1) Geçmiş bazlı fırsat
    if (
        previous_min is not None
        and previous_points >= 1
        and listing.price < previous_min
    ):
        discount_pct: Optional[float] = None
        if previous_min > 0:
            discount_pct = max(
                0.0, (previous_min - listing.price) / previous_min * 100
            )
        return Deal(
            listing=listing,
            historical_min=previous_min,
            history_points=previous_points,
            discount_pct=discount_pct,
        )

    # 2) Site bazlı fırsat — ürün kartında üstü çizili eski fiyat varsa
    op = listing.original_price
    if op is not None and op > listing.price:
        site_discount_pct = (op - listing.price) / op * 100
        # Çok ufak farkları (yuvarlama, kuruş) eleyelim
        if site_discount_pct >= 1.0:
            return Deal(
                listing=listing,
                historical_min=op,
                history_points=previous_points or 0,
                discount_pct=site_discount_pct,
            )

    return None

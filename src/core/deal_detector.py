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
    """Mevcut fiyat son `window_days` içindeki ÖNCEKİ en düşüğün ALTINA
    indiyse `Deal` döndür. Fiyat önceki min ile aynı (%0 değişim) ise
    fırsat sayılmaz — kullanıcı için gürültü olur.

    Önemli: `recorded_at` verilirse bu tarih/saatten **önceki** kayıtlar
    kullanılır. Scanner `record_listing` sonrası döndürdüğü timestamp'i
    burada geçerek "mevcut kaydı kendisiyle karşılaştırma" sorununun
    önüne geçer (indirim % her taramada azalmaz).

    Yeterli geçmiş (en az 1 ÖNCEKİ kayıt) yoksa None.
    """
    previous_min = db.previous_min_price(
        listing.url, window_days, before=recorded_at
    )
    previous_points = db.history_count(
        listing.url, window_days, before=recorded_at
    )

    # Önceki bir kayıt yoksa karşılaştırma yapamayız
    if previous_min is None or previous_points < 1:
        return None

    # Fiyat değişmemiş veya artmışsa fırsat değil (%0 indirimi filtrele)
    if listing.price >= previous_min:
        return None

    # İndirim % — ÖNCEKİ en düşüğe göre (sütun başlığıyla tutarlı)
    discount_pct: Optional[float] = None
    if previous_min > 0:
        discount_pct = max(0.0, (previous_min - listing.price) / previous_min * 100)

    return Deal(
        listing=listing,
        historical_min=previous_min,
        history_points=previous_points,
        discount_pct=discount_pct,
    )

"""Fırsat tespiti + referans fiyat doğrulaması (sahte indirim elemesi).

Sorun: siteler üstü çizili "eski fiyat"ı keyfi koyabiliyor. Tipik numaralar:
  - Kalıcı etiket: ürün aylardır aynı fiyatta ama sürekli "%40 indirim" yazıyor
    (üstü çizili fiyat hiç uygulanmamış).
  - Fiyat sıçratma: 60 günde bir 1 günlüğüne fiyatı yükseltip sonra
    "indirime" geri düşürme.

Kural (TR mevzuatındaki yaklaşımla aynı): indirimde referans alınacak önceki
fiyat, indirimden önceki **30 günün en düşük fiyatıdır**. 1 günlük sıçrama en
düşüğü değiştirmez; bu yüzden fiyat 30 günlük en düşüğün altına inmemişse
sayfa ne derse desin gerçek indirim yoktur.

Kararlar:
  verified   — fiyat önceki 30 günün en düşüğünün altında (indirim % buna göre)
               ya da son `window_days` içinde yeni dip.
  fake       — sayfada indirim etiketi var ama fiyat 30 günlük en düşüğün
               altında değil (yeterli geçmiş varsa).
  unverified — sayfada indirim etiketi var, doğrulayacak kadar geçmiş yok.
"""
from __future__ import annotations

import statistics
from datetime import datetime
from typing import Optional

from src.core.models import Deal, ProductListing
from src.storage.db import PriceDatabase

REF_DAYS = 30          # yasal referans penceresi
LOOKBACK_DAYS = 60     # etiket/sıçrama analizi penceresi
MIN_REF_POINTS = 5     # 30 günde en az bu kadar kayıt yoksa "doğrulanamadı"
MIN_DISCOUNT = 1.0     # %1 altı farklar (kuruş/yuvarlama) yok sayılır
INFLATED_GAP = 10.0    # iddia − gerçek > 10 puan → "etiket abartılı"
SPIKE_FACTOR = 1.15    # medyanın %15 üstü = sıçrama
SPIKE_MAX_RUN = 2      # en fazla 2 tarama süren yükseliş "kısa süreli"dir


def _tl(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"


def count_spikes(prices: list[float]) -> int:
    """Kısa süreli fiyat sıçramaları: medyanın %15 üstüne çıkıp en fazla 2
    tarama sonra geri dönen bölümler (seri sonundaki yükseliş sayılmaz)."""
    if len(prices) < 3:
        return 0
    limit = statistics.median(prices) * SPIKE_FACTOR
    spikes, run = 0, 0
    for p in prices:
        if p > limit:
            run += 1
        else:
            if 0 < run <= SPIKE_MAX_RUN:
                spikes += 1
            run = 0
    return spikes


def assess(
    price: float,
    original_price: Optional[float],
    prev_30: list[float],
    prev_60: list[float],
    *,
    window_min: Optional[float] = None,
) -> Optional[dict]:
    """Saf karar fonksiyonu. Fırsat/sahte değilse None döner.

    prev_30 / prev_60: mevcut kayıt HARİÇ, eskiden yeniye fiyatlar.
    window_min: config.history_days penceresindeki önceki en düşük.
    """
    claimed = None
    if original_price is not None and original_price > price:
        c = (original_price - price) / original_price * 100
        claimed = c if c >= MIN_DISCOUNT else None

    low30 = min(prev_30) if prev_30 else None
    spikes = count_spikes(prev_60)
    seen = None
    if original_price and prev_60:
        hits = sum(1 for p in prev_60 if p >= original_price * 0.97)
        seen = f"{hits}/{len(prev_60)}"

    new_low = window_min is not None and price < window_min
    honest = (low30 - price) / low30 * 100 if low30 else None
    base = {"claimed_pct": claimed, "ref_low_30d": low30, "badge_seen": seen, "spikes": spikes}

    # 1) Gerçek düşüş: 30 günlük en düşüğün altında ya da pencere içinde yeni dip
    if new_low or (honest is not None and honest >= MIN_DISCOUNT):
        pct = max(0.0, honest) if honest is not None else claimed
        reason = (f"Son 30 günün en düşüğü {_tl(low30)} → gerçek indirim %{pct:.1f}"
                  if low30 else "Fiyat yeni dip yaptı")
        if claimed is not None and pct is not None and claimed - pct > INFLATED_GAP:
            reason += f" (sayfa %{claimed:.0f} diyor — etiket abartılı)"
        return {**base, "verdict": "verified", "discount_pct": pct, "reason": reason}

    if claimed is None:
        return None

    # 2) Sayfada etiket var ama geçmiş doğrulamaya yetmiyor
    if len(prev_30) < MIN_REF_POINTS:
        return {**base, "verdict": "unverified", "discount_pct": claimed,
                "reason": f"Sayfa %{claimed:.0f} indirim diyor; doğrulamak için yeterli "
                          f"fiyat geçmişi yok ({len(prev_30)} kayıt)"}

    # 3) Sahte: fiyat 30 günlük en düşüğün altına inmemiş
    if price > low30 * 1.01:
        state = f"son 30 günün en düşüğünden ({_tl(low30)}) %{(price / low30 - 1) * 100:.0f} yüksek"
    else:
        state = f"zaten son 30 günün en düşük seviyesinde ({_tl(low30)})"
    reason = f"Sayfa %{claimed:.0f} indirim diyor ama fiyat {state} — gerçek indirim yok."
    if seen is not None:
        reason += f" Üstü çizili {_tl(original_price)} son 60 günde {seen} taramada görüldü."
    if spikes:
        reason += f" {spikes} kısa süreli fiyat sıçraması var."
    return {**base, "verdict": "fake", "discount_pct": 0.0, "reason": reason}


def detect_deal(
    db: PriceDatabase,
    listing: ProductListing,
    *,
    window_days: int = 30,
    recorded_at: Optional[datetime] = None,
) -> Optional[Deal]:
    """Ürün için fırsat kararı. Sahte indirimler de `verdict="fake"` ile döner;
    çağıran taraf gerçek fırsatları `deal.verdict != "fake"` ile süzer.

    `recorded_at` verilirse bu tarihten **önceki** kayıtlar kullanılır;
    scanner kendi yeni yazdığı kaydı hariç tutar.
    """
    previous_min = db.previous_min_price(listing.url, window_days, before=recorded_at)
    previous_points = db.history_count(listing.url, window_days, before=recorded_at)
    previous_logged = db.previous_logged_price(
        listing.url, before=recorded_at, different_from=listing.price
    )
    prev_30 = db.prices_before(listing.url, REF_DAYS, before=recorded_at)
    prev_60 = db.prices_before(listing.url, LOOKBACK_DAYS, before=recorded_at)

    a = assess(
        listing.price,
        listing.original_price,
        prev_30,
        prev_60,
        window_min=previous_min if previous_points >= 1 else None,
    )
    if a is None:
        return None
    return Deal(
        listing=listing,
        historical_min=previous_min,
        history_points=previous_points or 0,
        discount_pct=a["discount_pct"],
        original_price=listing.original_price,
        previous_logged_price=previous_logged,
        verdict=a["verdict"],
        claimed_pct=a["claimed_pct"],
        ref_low_30d=a["ref_low_30d"],
        badge_seen=a["badge_seen"],
        spikes=a["spikes"],
        reason=a["reason"],
    )

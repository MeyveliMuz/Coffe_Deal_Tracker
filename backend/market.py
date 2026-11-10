"""Piyasa normu: çekirdek kahvenin kilo fiyatı zaman içinde nerede?

Yöntem: her ürünün o aydaki medyan kilo fiyatı alınır (sık taranan ürün
ağırlık kazanmasın), sonra ürünler arası çeyreklikler hesaplanır:
ucuz dilim (alt %25), orta (medyan), pahalı dilim (üst %25).

Kilo fiyatı paket boyuna göre değişir (250 g paketin kilosu pahalıdır),
bu yüzden norm paket boyu kovasına göre hesaplanır; varsayılan ~1 kg.
"""
from __future__ import annotations

import sqlite3
import statistics
from collections import defaultdict
from typing import Optional

from src.core.weight import parse_weight
from src.scrapers.base import BaseScraper

from . import services

# id -> (etiket, alt sınır g, üst sınır g) — frontend'deki gramaj kovalarıyla aynı
SIZES = {
    "250": ("≤250 g", 0, 300),
    "500": ("500 g", 300, 700),
    "1000": ("1 kg", 700, 1300),
    "2000": ("2 kg+", 1300, 10**9),
}
MIN_PRODUCTS = 5  # bir ay/kova için en az bu kadar ürün yoksa norm verilmez


def size_of(total_g: Optional[int]) -> Optional[str]:
    if total_g is None:
        return None
    for sid, (_, lo, hi) in SIZES.items():
        if lo < total_g <= hi:
            return sid
    return None


def _quartiles(values: list[float]) -> Optional[tuple[float, float, float]]:
    if len(values) < MIN_PRODUCTS:
        return None
    q1, med, q3 = statistics.quantiles(values, n=4)
    return round(q1), round(med), round(q3)


def _rows(where: str = "", params: tuple = ()) -> list[tuple]:
    uri = "file:" + services.db_path().replace("\\", "/") + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as c:
            return c.execute(
                "SELECT p.url, p.name, p.brand, ph.price, ph.recorded_at "
                "FROM price_history ph JOIN products p ON p.url = ph.product_url " + where,
                params,
            ).fetchall()
    except sqlite3.OperationalError:  # DB henüz yok
        return []


def _bean_points(rows: list[tuple]) -> list[tuple[str, str, str, int, float]]:
    """(ay, url, marka, toplam_g, kilo_fiyatı) — yalnız çekirdek, gramajı bilinen."""
    out, cache = [], {}
    for url, name, brand, price, rec in rows:
        if url not in cache:
            w = parse_weight(name)
            ok = w is not None and BaseScraper._classify_product(name) == "cekirdek"
            cache[url] = w["total_g"] if ok else None
        g = cache[url]
        if g:
            out.append((str(rec)[:7], url, brand, g, price / g * 1000))
    return out


def overview(size: str = "1000") -> dict:
    """Aylık norm serisi + marka kırılımı (seçilen paket boyu için)."""
    if size not in SIZES:
        size = "1000"
    per: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    brand_of: dict[str, str] = {}
    for month, url, brand, g, ppk in _bean_points(_rows()):
        if size_of(g) == size:
            per[month][url].append(ppk)
            brand_of[url] = brand

    months = []
    for month in sorted(per):
        meds = [statistics.median(v) for v in per[month].values()]
        q = _quartiles(meds)
        if q:
            months.append({"month": month, "low": q[0], "mid": q[1], "high": q[2],
                           "products": len(meds)})

    brands = []
    if months:
        last = months[-1]["month"]
        prev = months[-2]["month"] if len(months) > 1 else None

        def by_brand(m: Optional[str]) -> dict[str, list[float]]:
            d: dict[str, list[float]] = defaultdict(list)
            for url, v in (per.get(m, {}) if m else {}).items():
                d[brand_of[url]].append(statistics.median(v))
            return d

        now, before = by_brand(last), by_brand(prev)
        for b in sorted(now, key=lambda b: statistics.median(now[b])):
            cur = round(statistics.median(now[b]))
            old = round(statistics.median(before[b])) if before.get(b) else None
            brands.append({
                "brand": b, "products": len(now[b]), "mid": cur,
                "min": round(min(now[b])), "max": round(max(now[b])),
                "change_pct": round((cur / old - 1) * 100, 1) if old else None,
            })
    return {"size": size, "size_label": SIZES[size][0], "months": months, "brands": brands,
            "sizes": [{"id": k, "label": v[0]} for k, v in SIZES.items()]}


def current_thresholds(days: int = 30) -> dict[str, tuple[float, float, float]]:
    """Paket boyu kovası başına son `days` günün (ucuz, orta, pahalı) eşikleri."""
    rows = _rows("WHERE ph.recorded_at >= datetime('now', ?)", (f"-{int(days)} days",))
    per: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for _month, url, _brand, g, ppk in _bean_points(rows):
        sid = size_of(g)
        if sid:
            per[sid][url].append(ppk)
    out = {}
    for sid, prods in per.items():
        q = _quartiles([statistics.median(v) for v in prods.values()])
        if q:
            out[sid] = q
    return out


def tier(price_per_kg: Optional[float], total_g: Optional[int], thresholds: dict) -> Optional[str]:
    """Ürünün kendi paket boyu normuna göre konumu: ucuz | orta | pahali."""
    q = thresholds.get(size_of(total_g) or "")
    if price_per_kg is None or q is None:
        return None
    return "ucuz" if price_per_kg <= q[0] else "pahali" if price_per_kg >= q[2] else "orta"

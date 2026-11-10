"""Yapay zekâ (Gemini) harcama takibi ve bakiyeyi bir bitiş tarihine yayan bütçe.

Her Gemini çağrısının token kullanımı `llm_usage` tablosuna, aşağıdaki fiyat
tablosuyla hesaplanmış dolar maliyetiyle yazılır.

Bütçe sabit bir aylık tutar değil, **cüzdan** üzerinden hesaplanır
(`data/ai_wallet.json`): AI Studio'daki bakiye, o bakiyenin okunduğu an ve
paranın yetmesi gereken tarih. Her ayın payı = ay başındaki tahmini bakiye ×
(bu ayın gün sayısı / bitişe kalan gün). Az harcanan ay sonraki aylara kalır,
çok harcanan ay sonrakileri kısar — böylece para tam bitiş tarihine yeter.

Takip edilen maliyet gerçeği tam tutmayabilir (fiyatlar 3. taraf kaynaklı,
KDV vb.). Bu yüzden takip edilen tutar `cost_factor` ile çarpılır; kullanıcı
AI Studio'daki güncel bakiyeyi girdikçe (`set_balance`) katsayı gerçek
düşüşe göre kendini düzeltir ve bakiye yeniden çapalanır.

  - Sınıflandırma, ayın payının %60'ı dolunca durur (sohbete yer kalsın).
  - Sohbet, ayın payı tamamen dolunca durur.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.classify import GeminiClient
from src.storage.db import PriceDatabase

from . import services

PRICES: dict[str, tuple[float, float]] = {
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.1-flash-lite-preview": (0.25, 1.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-3.8-flash": (1.50, 7.50),   # tanıtım fiyatı 0.75/3.75 (31.12.2026'ya kadar) — temkinli
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "gemini-pro-latest": (2.00, 12.00),
}
FALLBACK_PRICE = (2.00, 12.00)
CLASSIFY_SHARE = 0.60  # sınıflandırmanın kullanabileceği bütçe payı

# Sohbet modeli bütçeye göre: ay başında en akıllı model, ayın payının yarısı
# dolunca tasarruf modeli. 2026-11 testi (4 senaryo, araç kullanımı): 3.8 Flash
# 4/4, ~0,85 TL/mesaj; 3.1 Flash-Lite 4/4 (prompt düzeltmesinden sonra), ~0,10 TL/mesaj.
CHAT_PRIMARY = "gemini-3.8-flash"
CHAT_ECONOMY = "gemini-3.1-flash-lite"
ECONOMY_AFTER = 0.50

# Cüzdan dosyası yoksa (yeni kurulum) kullanılacak sabit aylık sınır
FALLBACK_MONTHLY_TRY = 60.0
DEFAULT_COST_FACTOR = 1.3
# Katsayı ancak yeterli veri varsa güncellenir; Google'ın faturası birkaç saat
# geriden geldiği için çok kısa aralıklar katsayıyı yanlış düşürür.
CALIBRATE_MIN_DAYS = 3
CALIBRATE_MIN_TRY = 5.0


def cost_usd(model: str, tin: int, tout: int) -> float:
    pin, pout = PRICES.get(model, FALLBACK_PRICE)
    return (tin * pin + tout * pout) / 1_000_000


def _record(client: GeminiClient, tin: int, tout: int) -> None:
    db = PriceDatabase(services.db_path())
    try:
        db.add_llm_usage(client.model, client.purpose, tin, tout, cost_usd(client.model, tin, tout))
    finally:
        db.close()


def install() -> None:
    """Tüm GeminiClient çağrılarının kullanımını DB'ye yazdır (backend açılışında)."""
    GeminiClient.usage_sink = staticmethod(_record)


# --- cüzdan -------------------------------------------------------------------
def _wallet_path() -> Path:
    return Path(services.db_path()).parent / "ai_wallet.json"


def load_wallet() -> Optional[dict]:
    """{balance_try, balance_at (ISO), until (YYYY-MM-DD), cost_factor} ya da None."""
    try:
        w = json.loads(_wallet_path().read_text(encoding="utf-8"))
        return {"balance_try": float(w["balance_try"]), "balance_at": str(w["balance_at"]),
                "until": str(w["until"]), "cost_factor": float(w.get("cost_factor", DEFAULT_COST_FACTOR))}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _save_wallet(w: dict) -> None:
    p = _wallet_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def _tracked_try(since: datetime, usd_try: float) -> dict[str, dict]:
    """Takip edilen (katsayısız) harcama, amaç bazında, `since`'ten beri."""
    db = PriceDatabase(services.db_path())
    try:
        rows = db.llm_usage_since(since)
    finally:
        db.close()
    return {p: {"calls": n, "input_tokens": i or 0, "output_tokens": o or 0, "cost_try": (c or 0) * usd_try}
            for p, n, i, o, c in rows}


def _total(by: dict[str, dict]) -> float:
    return sum(v["cost_try"] for v in by.values())


def set_balance(balance_try: float, until: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """AI Studio'daki güncel bakiyeyi kaydet (yeniden çapala). Önceki çapadan bu
    yana yeterince harcama olduysa gerçek düşüşe göre maliyet katsayısını düzelt."""
    if not 0 <= balance_try < 1_000_000:
        raise ValueError("bakiye 0 ile 1.000.000 TL arasında olmalı")
    now = now or datetime.now()
    old = load_wallet()
    factor = old["cost_factor"] if old else DEFAULT_COST_FACTOR
    if until:
        datetime.strptime(until, "%Y-%m-%d")  # biçim kontrolü
    until = until or (old["until"] if old else None)
    if not until:
        raise ValueError("ilk kayıtta bitiş tarihi (until, YYYY-MM-DD) gerekli")
    calibrated = False
    if old:
        since = datetime.fromisoformat(old["balance_at"])
        tracked = _total(_tracked_try(since, services.load_config().usd_try))
        drop = old["balance_try"] - balance_try
        if (now - since).days >= CALIBRATE_MIN_DAYS and tracked >= CALIBRATE_MIN_TRY and drop > 0:
            measured = drop / tracked
            factor = round(min(3.0, max(1.0, 0.5 * factor + 0.5 * measured)), 3)
            calibrated = True
    w = {"balance_try": round(balance_try, 2), "balance_at": now.isoformat(timespec="seconds"),
         "until": until, "cost_factor": factor}
    _save_wallet(w)
    return {**w, "calibrated": calibrated}


# --- durum --------------------------------------------------------------------
def month_start(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(d: datetime) -> datetime:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def status(now: Optional[datetime] = None) -> dict:
    now = now or datetime.now()
    cfg = services.load_config()
    w = load_wallet()
    ms = month_start(now)
    if not w:
        by = _tracked_try(ms, cfg.usd_try)
        spent, budget, factor, extra = _total(by), FALLBACK_MONTHLY_TRY, 1.0, {}
    else:
        factor = w["cost_factor"]
        anchor = datetime.fromisoformat(w["balance_at"])
        end = datetime.strptime(w["until"], "%Y-%m-%d") + timedelta(days=1)  # bitiş günü dahil
        period_start = max(ms, anchor)
        since_anchor = factor * _total(_tracked_try(anchor, cfg.usd_try))
        by = _tracked_try(period_start, cfg.usd_try)
        spent = factor * _total(by)
        balance_now = w["balance_try"] - since_anchor
        at_period_start = balance_now + spent
        if period_start >= end:  # bitiş tarihi geçti: kalanı bu aya ver
            budget = max(0.0, at_period_start)
        else:
            share = (min(_next_month(ms), end) - period_start) / (end - period_start)
            budget = max(0.0, at_period_start * share)
        extra = {"balance_est_try": round(max(0.0, balance_now), 2), "balance_at": w["balance_at"],
                 "until": w["until"]}
    for v in by.values():
        v["cost_try"] = round(v["cost_try"] * factor, 2)
    out = {"month": ms.strftime("%Y-%m"), "spent_try": round(spent, 2), "budget_try": round(budget, 2),
           "remaining_try": round(max(0.0, budget - spent), 2), "usd_try": cfg.usd_try,
           "cost_factor": factor, "by_purpose": by, **extra}
    out["chat_model"], out["chat_mode"] = chat_model(out)
    return out


def chat_model(s: Optional[dict] = None) -> tuple[str, str]:
    """(model, mod) — mod: 'akıllı' ya da 'tasarruf'."""
    s = s or status()
    if s["spent_try"] < s["budget_try"] * ECONOMY_AFTER:
        return CHAT_PRIMARY, "akıllı"
    return CHAT_ECONOMY, "tasarruf"


def allowed(purpose: str) -> bool:
    s = status()
    limit = s["budget_try"] * (CLASSIFY_SHARE if purpose == "classify" else 1.0)
    return s["spent_try"] < limit

"""Kahve profili zenginleştirme (Gemini) — arka plan işi + durum.

Tarama ürün sayfası açıklamalarını DB'ye yazar (scan_engine._fetch_details);
bu modül açıklaması olup profili olmayanları Gemini ile sınıflandırır.
Senkron HTTP çağrıları event loop'u bloklamasın diye thread'de çalışır.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from src.core.classify import classify_pending, load_api_key
from src.storage.db import PriceDatabase

from . import budget, services

log = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None
_last: dict = {}


def running() -> bool:
    return _task is not None and not _task.done()


def start(limit: int = 80) -> bool:
    """Arka planda sınıflandırmayı başlat. Zaten çalışıyorsa ya da anahtar yoksa False."""
    global _task
    if running() or not load_api_key() or not budget.allowed("classify"):
        return False

    async def _run() -> None:
        global _last
        try:
            res = await asyncio.to_thread(
                classify_pending, services.db_path(), limit, lambda: budget.allowed("classify")
            )
        except Exception as exc:  # son çare — tarama/sunucu etkilenmesin
            log.exception("Profil zenginleştirme çöktü")
            res = {"status": "error", "classified": 0, "errors": [str(exc)[:200]]}
        _last = {**res, "finished_at": datetime.now().isoformat(timespec="seconds")}

    _task = asyncio.create_task(_run())
    return True


def status() -> dict:
    db = PriceDatabase(services.db_path())
    try:
        stats = db.details_stats()
    finally:
        db.close()
    return {**stats, "has_key": bool(load_api_key()), "running": running(), "last": _last}


def profiles() -> dict[str, dict]:
    """url -> profil sözlüğü (ürün listelerine eklemek için)."""
    db = PriceDatabase(services.db_path())
    try:
        raw = db.all_profiles()
    finally:
        db.close()
    out = {}
    for url, text in raw.items():
        try:
            out[url] = json.loads(text)
        except (TypeError, ValueError):
            continue
    return out

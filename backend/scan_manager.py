"""Tarama job yöneticisi + WebSocket yayını.

`run_scan` çekirdeğini bir asyncio task'ı olarak çalıştırır; tarama
olaylarını (progress/product/deal/error/finished) bağlı tüm WebSocket
istemcilerine yayar. Aynı anda yalnızca bir tarama çalışır.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from src.core.config import AppConfig
from src.core.scan_engine import run_scan

from .schemas import deal_to_dict, product_to_dict, summary_to_dict

log = logging.getLogger(__name__)


class ScanManager:
    def __init__(self) -> None:
        self._clients: set = set()
        self._task: Optional[asyncio.Task] = None
        self._broadcaster: Optional[asyncio.Task] = None
        self._queue: Optional[asyncio.Queue] = None
        self._cancelled = False

        self.status: str = "idle"  # idle | running | done | error
        self.last_progress: str = ""
        self.products_found = 0
        self.deals_found = 0
        self.sites_scanned = 0
        self.errors: list[str] = []
        self.skipped: list[str] = []
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None

    # -- durum ---------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status_dict(self) -> dict:
        return {
            "status": self.status,
            "running": self.running,
            "last_progress": self.last_progress,
            "products_found": self.products_found,
            "deals_found": self.deals_found,
            "sites_scanned": self.sites_scanned,
            "errors": list(self.errors),
            "skipped": list(self.skipped),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

    # -- WebSocket istemcileri ----------------------------------------------
    async def connect(self, ws) -> None:
        await ws.accept()
        self._clients.add(ws)
        # Yeni bağlanana mevcut durumu gönder
        try:
            await ws.send_json({"type": "status", **self.status_dict()})
        except Exception:
            self._clients.discard(ws)

    def disconnect(self, ws) -> None:
        self._clients.discard(ws)

    # -- tarama --------------------------------------------------------------
    def start(self, config: AppConfig, db_path: str) -> bool:
        """Tarama başlat. Zaten çalışıyorsa False döner."""
        if self.running:
            return False
        self._cancelled = False
        self.status = "running"
        self.last_progress = ""
        self.products_found = 0
        self.deals_found = 0
        self.sites_scanned = 0
        self.errors = []
        self.skipped = []
        self.started_at = datetime.now()
        self.finished_at = None
        self._queue = asyncio.Queue()
        self._broadcaster = asyncio.create_task(self._run_broadcaster())
        self._task = asyncio.create_task(self._run(config, db_path))
        return True

    def cancel(self) -> None:
        self._cancelled = True

    def _put(self, event: Optional[dict]) -> None:
        if self._queue is not None:
            self._queue.put_nowait(event)

    async def _run(self, config: AppConfig, db_path: str) -> None:
        def on_progress(msg: str) -> None:
            self.last_progress = msg
            self._put({"type": "progress", "message": msg})

        def on_product(listing) -> None:
            self.products_found += 1
            self._put(
                {
                    "type": "product",
                    "product": product_to_dict(listing),
                    "products_found": self.products_found,
                }
            )

        def on_deal(deal) -> None:
            self.deals_found += 1
            self._put(
                {
                    "type": "deal",
                    "deal": deal_to_dict(deal),
                    "deals_found": self.deals_found,
                }
            )

        def on_error(msg: str) -> None:
            self.errors.append(msg)
            self._put({"type": "error", "message": msg})

        try:
            summary = await run_scan(
                config,
                db_path,
                on_progress=on_progress,
                on_product=on_product,
                on_deal=on_deal,
                on_error=on_error,
                should_cancel=lambda: self._cancelled,
            )
            self.sites_scanned = summary.sites_scanned
            self.skipped = list(summary.skipped)
            self.finished_at = summary.finished_at or datetime.now()
            self.status = "error" if summary.errors and summary.products_found == 0 else "done"
            self._put({"type": "finished", "summary": summary_to_dict(summary)})
        except Exception as exc:  # son çare
            log.exception("Tarama job'u çöktü")
            self.status = "error"
            self.finished_at = datetime.now()
            self._put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
            self._put({"type": "finished", "summary": None})
        finally:
            self._put(None)  # broadcaster'ı durdur

    async def _run_broadcaster(self) -> None:
        assert self._queue is not None
        while True:
            event = await self._queue.get()
            if event is None:
                break
            dead = []
            for ws in list(self._clients):
                try:
                    await ws.send_json(event)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)


# Tekil (uygulama genelinde tek tarama)
manager = ScanManager()

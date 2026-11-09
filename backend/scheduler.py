"""Sunucu tarafı zamanlanmış tarama (APScheduler).

config'deki `schedule_enabled` + `schedule_time` (HH:MM) değerlerine göre her
gün belirtilen saatte taramayı tetikler. Tarama zaten çalışıyorsa atlar.

Telafi (catch-up): PC o saatte kapalı/uykudaysa günlük tetik kaçar. Bu yüzden
backend açılınca ve her `CATCHUP_EVERY_MIN` dakikada bir "bugünün tarama saati
geçti ama o saatten beri hiç fiyat kaydı yok mu?" diye bakılır; öyleyse hemen
taranır. Son tarama zamanı DB'deki son fiyat kaydıdır — elle başlatılan
taramalar da sayılır, aynı gün çift tarama olmaz.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.core.config import AppConfig

from . import services
from .scan_manager import manager

log = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None
_JOB_ID = "daily_scan"
_CATCHUP_ID = "catchup_scan"
CATCHUP_EVERY_MIN = 10        # telafi kontrol sıklığı
CATCHUP_FIRST_DELAY_S = 120   # açılıştan sonra ağın gelmesi için bekle
CATCHUP_RETRY_MIN = 30        # başarısız (veri yazmayan) denemeden sonra tekrar
_last_catchup_attempt: Optional[datetime] = None


def _parse_hm(value: str) -> tuple[int, int]:
    try:
        h, m = value.split(":")
        return max(0, min(23, int(h))), max(0, min(59, int(m)))
    except Exception:
        return 9, 0


def is_scan_due(now: datetime, schedule_time: str, last_scan: Optional[datetime]) -> bool:
    """Bugünün tarama saati geçti ve o saatten beri tarama yoksa True."""
    h, m = _parse_hm(schedule_time)
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return now >= target and (last_scan is None or last_scan < target)


def _last_scan_time() -> Optional[datetime]:
    """DB'deki son fiyat kaydının zamanı (son başarılı tarama)."""
    try:
        with sqlite3.connect(services.db_path()) as c:
            row = c.execute("SELECT MAX(recorded_at) FROM price_history").fetchone()
        return datetime.fromisoformat(str(row[0])) if row and row[0] else None
    except Exception:
        log.exception("Son tarama zamanı okunamadı")
        return None


async def _catchup_check() -> None:
    global _last_catchup_attempt
    cfg = services.load_config()
    if not cfg.schedule_enabled or manager.running:
        return
    now = datetime.now()
    last = _last_scan_time()
    if not is_scan_due(now, cfg.schedule_time, last):
        return
    if _last_catchup_attempt and now - _last_catchup_attempt < timedelta(minutes=CATCHUP_RETRY_MIN):
        return  # az önce denendi (ör. internet yoktu); hemen tekrar zorlamayalım
    _last_catchup_attempt = now
    log.info("Kaçırılan günlük tarama telafi ediliyor (saat %s, son tarama %s)",
             cfg.schedule_time, last.strftime("%Y-%m-%d %H:%M") if last else "yok")
    manager.start(cfg, services.db_path())


async def _scheduled_scan() -> None:
    if manager.running:
        log.info("Zamanlanmış tarama atlandı — zaten çalışıyor")
        return
    log.info("Zamanlanmış tarama başlatılıyor")
    manager.start(services.load_config(), services.db_path())


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        _scheduler.start()
        _scheduler.add_job(
            _catchup_check,
            IntervalTrigger(minutes=CATCHUP_EVERY_MIN),
            id=_CATCHUP_ID,
            next_run_time=datetime.now() + timedelta(seconds=CATCHUP_FIRST_DELAY_S),
            replace_existing=True,
        )
    reschedule(services.load_config())


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def reschedule(cfg: AppConfig) -> None:
    """config değişince çağrılır: job'u kaldır, gerekiyorsa yeniden kur."""
    if _scheduler is None:
        return
    existing = _scheduler.get_job(_JOB_ID)
    if existing:
        _scheduler.remove_job(_JOB_ID)
    if cfg.schedule_enabled:
        hour, minute = _parse_hm(cfg.schedule_time)
        _scheduler.add_job(
            _scheduled_scan,
            CronTrigger(hour=hour, minute=minute),
            id=_JOB_ID,
            replace_existing=True,
            misfire_grace_time=3600,  # uykudan 1 saat içinde uyanırsa yine çalışsın
            coalesce=True,
        )
        log.info("Zamanlanmış tarama kuruldu: her gün %02d:%02d", hour, minute)


def next_run() -> Optional[str]:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(_JOB_ID)
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None

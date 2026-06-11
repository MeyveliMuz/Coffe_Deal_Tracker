"""Sunucu tarafı zamanlanmış tarama (APScheduler).

config'deki `schedule_enabled` + `schedule_time` (HH:MM) değerlerine göre her
gün belirtilen saatte taramayı tetikler. Tarama zaten çalışıyorsa atlar.
"""
from __future__ import annotations

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core.config import AppConfig

from . import services
from .scan_manager import manager

log = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None
_JOB_ID = "daily_scan"


def _parse_hm(value: str) -> tuple[int, int]:
    try:
        h, m = value.split(":")
        return max(0, min(23, int(h))), max(0, min(59, int(m)))
    except Exception:
        return 9, 0


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
        )
        log.info("Zamanlanmış tarama kuruldu: her gün %02d:%02d", hour, minute)


def next_run() -> Optional[str]:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(_JOB_ID)
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None

"""Uygulama çalışma-zamanı durumu (kullanıcı ayarı DEĞİL).

Şimdilik yalnızca "son otomatik taramanın yapıldığı gün"ü tutar; böylece
otomatik tarama günde en fazla bir kez (o gün ilk açılışta) çalışır.
`data/app_state.json` içine yazılır — config.json'dan ayrı, gitignore'da."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from src.core.config import project_root

log = logging.getLogger(__name__)

_KEY_LAST_AUTOSCAN = "last_autoscan_date"


def _state_path() -> Path:
    return project_root() / "data" / "app_state.json"


def _read() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        log.warning("app_state.json okunamadı, sıfırlanıyor", exc_info=True)
        return {}


def _write(data: dict) -> None:
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        log.warning("app_state.json yazılamadı", exc_info=True)


def has_autoscanned_today() -> bool:
    """Bugün otomatik tarama yapıldı mı?"""
    return _read().get(_KEY_LAST_AUTOSCAN) == date.today().isoformat()


def mark_autoscanned_today() -> None:
    """Bugünü 'otomatik tarama yapıldı' olarak işaretle."""
    data = _read()
    data[_KEY_LAST_AUTOSCAN] = date.today().isoformat()
    _write(data)

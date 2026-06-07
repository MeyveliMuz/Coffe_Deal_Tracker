"""Windows oturum açılışında otomatik başlatma.

HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run altına bir değer
yazarak kullanıcı oturum açtığında uygulamayı başlatır. Yönetici yetkisi
gerektirmez (HKCU). Komut satırına `--autoscan` eklenir; uygulama bu argümanı
görünce açılışta tek seferlik bir tarama yapar.

Yalnızca Windows'ta anlamlı; başka platformda fonksiyonlar sessizce no-op.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "CoffeeDealTracker"


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _launch_command() -> str:
    """Registry'ye yazılacak komut satırı (tırnaklı, --autoscan ekli)."""
    if getattr(sys, "frozen", False):
        # Paketli .exe — doğrudan kendisini çağır
        exe = Path(sys.executable).resolve()
        return f'"{exe}" --autoscan'

    # Geliştirme modu — pythonw ile (konsolsuz) main.py'yi çalıştır
    py_dir = Path(sys.executable).resolve().parent
    pythonw = py_dir / "pythonw.exe"
    interpreter = pythonw if pythonw.exists() else Path(sys.executable).resolve()
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{interpreter}" "{main_py}" --autoscan'


def is_enabled() -> bool:
    """Otomatik başlatma kayıtlı mı?"""
    if not _is_windows():
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        log.exception("Otomatik başlatma durumu okunamadı")
        return False


def enable() -> bool:
    """Otomatik başlatmayı aç. Başarılıysa True döner."""
    if not _is_windows():
        log.info("Otomatik başlatma yalnızca Windows'ta desteklenir")
        return False
    try:
        import winreg

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
        log.info("Otomatik başlatma açıldı: %s", _launch_command())
        return True
    except OSError:
        log.exception("Otomatik başlatma açılamadı")
        return False


def disable() -> bool:
    """Otomatik başlatmayı kapat. Zaten kapalıysa da True döner."""
    if not _is_windows():
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
        log.info("Otomatik başlatma kapatıldı")
        return True
    except FileNotFoundError:
        return True  # zaten yok
    except OSError:
        log.exception("Otomatik başlatma kapatılamadı")
        return False


def set_enabled(enabled: bool) -> bool:
    return enable() if enabled else disable()

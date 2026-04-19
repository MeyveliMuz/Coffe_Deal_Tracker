import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# PyInstaller --noconsole modunda stdout/stderr None olabilir; Playwright
# alt süreci bu pipe'ları miras aldığında çökebilir. Erken NUL'a yönlendir.
if sys.stdout is None or sys.stderr is None:
    devnull = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = devnull
    if sys.stderr is None:
        sys.stderr = devnull


def _configure_playwright_browsers_path() -> Path:
    """Playwright tarayıcı konumu.

    Öncelik sırası:
    1. Kullanıcı PLAYWRIGHT_BROWSERS_PATH'i set etmişse ona saygı göster
    2. Paketli (frozen) modda: exe yanındaki `browsers/` klasörü (varsa)
    3. Dev modda veya portable klasör yoksa: %LOCALAPPDATA%\\ms-playwright
    """
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])

    # Paketli modda exe'nin yanındaki browsers/ dizinini tercih et
    if getattr(sys, "frozen", False):
        portable = Path(sys.executable).resolve().parent / "browsers"
        if portable.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(portable)
            return portable

    local_app = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or ""
    browsers_root = Path(local_app) / "ms-playwright"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_root)
    return browsers_root


_BROWSERS_ROOT = _configure_playwright_browsers_path()


from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import project_root
from src.ui.main_window import MainWindow


def _icon_path() -> Path | None:
    """İkon dosyasını bul. Paketli modda bundle içinde, dev modda repo'da."""
    candidates = []
    if getattr(sys, "frozen", False):
        # PyInstaller --add-data "assets/icon.ico;assets" ile buraya koyuyor
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        if meipass:
            candidates.append(meipass / "assets" / "icon.ico")
        candidates.append(Path(sys.executable).resolve().parent / "assets" / "icon.ico")
    candidates.append(Path(__file__).resolve().parent.parent / "assets" / "icon.ico")
    for p in candidates:
        if p.exists():
            return p
    return None


def _setup_logging() -> Path:
    """Logları hem konsola hem `data/app.log` dosyasına yaz."""
    log_dir = project_root() / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Önceki handler'ları temizle (çift log olmasın)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    logging.getLogger(__name__).info("Coffee Deal Tracker başlıyor; log: %s", log_path)
    return log_path


def main() -> int:
    log_path = _setup_logging()
    log = logging.getLogger(__name__)
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Coffee Deal Tracker")
        # Uygulama ikonu — pencere + Windows görev çubuğu için
        icon_path = _icon_path()
        if icon_path is not None:
            app.setWindowIcon(QIcon(str(icon_path)))
            log.info("İkon yüklendi: %s", icon_path)
        else:
            log.warning("İkon bulunamadı; varsayılan kullanılacak")
        # Açık olarak set et — son pencere kapanana kadar event loop döner.
        # PyInstaller + PySide6 kombosunda bazen default davranış değişebiliyor.
        app.setQuitOnLastWindowClosed(True)
        app.aboutToQuit.connect(lambda: log.info("aboutToQuit sinyali alındı"))
        window = MainWindow()
        if icon_path is not None:
            window.setWindowIcon(QIcon(str(icon_path)))
        window.log_path = log_path  # UI log yolunu gösterebilsin
        window.show()
        log.info("QApplication.exec() başlıyor")
        rc = app.exec()
        log.info("QApplication.exec() döndü, rc=%s", rc)
        return int(rc)
    except Exception:
        log.exception("Fatal error on startup")
        # --noconsole modunda traceback görünmüyordu; log dosyasına düştü.
        # Son çare: Qt hâlâ ayaktaysa popup göster.
        try:
            from PySide6.QtWidgets import QApplication as _QA, QMessageBox as _QMB
            _app = _QA.instance() or _QA(sys.argv)
            _QMB.critical(
                None,
                "Coffee Deal Tracker — Fatal Error",
                f"Uygulama başlatılırken hata oluştu.\n\nLog: {log_path}",
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())

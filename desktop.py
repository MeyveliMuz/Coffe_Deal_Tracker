"""Masaüstü kabuğu (Faz 7).

PC uygulamasını açınca: backend (FastAPI) bir arka plan thread'inde başlar ve
web arayüzü ayrı bir tarayıcı yerine UYGULAMANIN KENDİ PENCERESİNDE gösterilir
(PySide6 QtWebEngine ile gömülü Chromium). "Sunucu URL'i gir" derdi yok — app
otomatik kendi backend'ini ayağa kaldırıp ona bağlanır.

Çalıştırma:
    npm --prefix frontend run build      # bir kez (frontend/dist üretir)
    py -3.14 desktop.py
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Konsol cp1252 olabilir; Türkçe karakterli loglar çökmesin diye UTF-8'e çevir.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

# QtWebEngine'in bazı Windows/GPU kombinasyonlarında sessizce çökmesini önle:
# yazılımsal render + sandbox kapalı (yerel, güvenli).
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")

PORT = 8000
URL = f"http://127.0.0.1:{PORT}"
LOG = ROOT / "data" / "desktop.log"


def _log(msg: str) -> None:
    try:
        if sys.stdout is not None:
            print(msg, flush=True)
    except Exception:
        pass
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _start_backend() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=PORT, log_level="warning")


def _wait_backend(timeout_s: int = 30) -> bool:
    for _ in range(timeout_s * 2):
        try:
            urllib.request.urlopen(f"{URL}/api/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> int:
    dist = ROOT / "frontend" / "dist"
    if not dist.exists():
        _log("HATA: frontend/dist yok. Önce: npm --prefix frontend run build")
        return 1

    threading.Thread(target=_start_backend, daemon=True).start()
    if not _wait_backend():
        _log("Backend zamanında başlamadı.")
        return 1
    _log("Backend hazır, pencere açılıyor...")

    try:
        from PySide6.QtCore import QCoreApplication, Qt, QUrl
        # QtWebEngine için paylaşılan OpenGL context'i — QApplication'dan ÖNCE
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

        from PySide6.QtGui import QIcon
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import QApplication, QMainWindow

        app = QApplication(sys.argv)
        app.setApplicationName("Coffee Deal Tracker")

        if sys.platform.startswith("win"):
            try:
                import ctypes

                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "MeyveliMuz.CoffeeDealTracker.Desktop"
                )
            except Exception:
                pass

        icon_path = ROOT / "assets" / "icon.ico"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

        win = QMainWindow()
        win.setWindowTitle("Coffee Deal Tracker")
        win.resize(1200, 820)
        if icon_path.exists():
            win.setWindowIcon(QIcon(str(icon_path)))

        view = QWebEngineView()
        view.load(QUrl(URL))
        win.setCentralWidget(view)
        win.show()
        win.raise_()
        win.activateWindow()
        _log("Pencere gösterildi (exec).")
        return app.exec()
    except Exception:
        _log("Qt penceresi açılamadı:\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())

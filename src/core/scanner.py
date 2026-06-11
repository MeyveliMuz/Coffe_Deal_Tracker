"""Qt adaptörü: framework-bağımsız `run_scan` çekirdeğini QThread + Signal'lere bağlar.

Asıl tarama mantığı `src/core/scan_engine.py` içindedir; burada yalnızca
çekirdeğin callback'lerini Qt sinyallerine çeviririz. Böylece aynı tarama
mantığı hem masaüstü (Qt) hem de ileride web backend (FastAPI) tarafından
paylaşılır.
"""
from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import QObject, QThread, Signal

from src.core.config import AppConfig
from src.core.models import ScanSummary

# Geriye dönük uyumluluk: bu isimler eskiden scanner.py'de tanımlıydı.
# Artık scan_engine'den geliyor ama buradan da erişilebilsin.
from src.core.scan_engine import (  # noqa: F401
    SCRAPER_REGISTRY,
    register_default_scrapers,
    run_scan,
)


log = logging.getLogger(__name__)


class ScanWorker(QObject):
    """QThread içinde çalışan iş parçacığı. Sinyaller UI thread'ine gider.

    İnce bir adaptör: `run_scan` çekirdeğini çağırır ve callback'leri
    Qt sinyallerine çevirir.
    """

    # UI'ya yayınlanan sinyaller
    progress = Signal(str)                      # ör. "Trendyol · meinl taranıyor..."
    product_found = Signal(object)              # ProductListing
    deal_found = Signal(object)                 # Deal
    error = Signal(str)
    finished = Signal(object)                   # ScanSummary

    def __init__(self, config: AppConfig, db_path: str) -> None:
        super().__init__()
        self._config = config
        self._db_path = db_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    # QThread bağlı slot
    def run(self) -> None:
        log.info("ScanWorker.run() başladı")
        try:
            summary = asyncio.run(
                run_scan(
                    self._config,
                    self._db_path,
                    on_progress=self.progress.emit,
                    on_product=self.product_found.emit,
                    on_deal=self.deal_found.emit,
                    on_error=self.error.emit,
                    should_cancel=lambda: self._cancelled,
                )
            )
        except Exception as exc:  # son çare — run_scan normalde fırlatmaz
            log.exception("ScanWorker crashed")
            msg = f"Tarama başarısız ({type(exc).__name__}): {exc}"
            self.error.emit(msg)
            summary = ScanSummary(errors=[msg])
        finally:
            log.info("ScanWorker.run() çıkıyor")
        self.finished.emit(summary)


def start_scan_thread(config: AppConfig, db_path: str) -> tuple[QThread, ScanWorker]:
    """ScanWorker'ı bir QThread'e taşır ve başlatır. Caller thread/worker
    referanslarını TUTMALI — aksi halde Qt C++ objesi silinir ve sinyal
    sistemi dangling olur.

    NOT: `deleteLater` bağlantıları KASITLI OLARAK yok. PyInstaller ile
    paketlenmiş PySide6 + QThread kombinasyonunda `finished → deleteLater`
    zinciri sessiz native crash'e sebep oluyordu (Qt objesi silinirken
    Python tarafı hâlâ ref tutuyor → double-free). Objeleri canlı tutup
    app kapanınca Qt'nin toplu temizliğine bırakıyoruz.
    """
    thread = QThread()
    worker = ScanWorker(config, db_path)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    # NOT: worker.deleteLater / thread.deleteLater BAĞLANMIYOR — üstteki nota bakın.
    thread.start()
    return thread, worker

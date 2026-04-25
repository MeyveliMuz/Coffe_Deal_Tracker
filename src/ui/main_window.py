"""Ana pencere: başlat butonu, sekmeli tablo, durum çubuğu."""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.config import AppConfig, default_config_path, default_db_path
from src.core.deal_detector import detect_deal
from src.core.models import Deal, ProductListing, ScanSummary
from src.core.scanner import ScanWorker, start_scan_thread
from src.storage.db import PriceDatabase
from src.ui.deal_table import DealTable


log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Coffee Deal Tracker")
        self.resize(1100, 680)

        self._config = AppConfig.load(default_config_path())
        self._db_path = str(default_db_path())

        self._thread: Optional[QThread] = None
        self._worker: Optional[ScanWorker] = None
        # Eski thread/worker'ları canlı tutmak için (Qt C++ objesi
        # silinmesin diye). PyInstaller'da deleteLater çöküyor — bkz.
        # start_scan_thread'daki not. Liste app ömrü boyunca birikir
        # (3-5 eleman kadar, zararsız).
        self._old_threads: list[QThread] = []
        self._old_workers: list[ScanWorker] = []
        self._errors: list[str] = []
        self._skipped: list[str] = []
        self.log_path = None  # main.py tarafından set edilir

        self._build_ui()
        # Önceki taramanın sonuçlarını DB'den yükle — kullanıcı app'i her
        # açtığında son N saatin ürünleri tabloda hazır gelsin.
        self._load_last_snapshot()

    # -- UI --------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # Üst çubuk: başlık + buton
        top = QHBoxLayout()
        title = QLabel("☕ Coffee Deal Tracker")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        top.addWidget(title)
        top.addStretch(1)

        self.scan_button = QPushButton("Taramayı Başlat")
        self.scan_button.setMinimumWidth(160)
        self.scan_button.setMinimumHeight(34)
        self.scan_button.clicked.connect(self._on_scan_clicked)
        top.addWidget(self.scan_button)
        root.addLayout(top)

        subtitle = QLabel(
            f"Siteler: {', '.join(s.title() for s in self._config.sites)}  ·  "
            f"Markalar: {', '.join(b.title() for b in self._config.brands)}  ·  "
            f"Pencere: {self._config.history_days} gün"
        )
        subtitle.setStyleSheet("color: #666;")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # İlk kullanıcı açıklama bandı
        self.banner = QLabel(
            "ℹ Fırsatlar sekmesi iki durumda dolar: "
            f"(1) ürünün fiyatı son {self._config.history_days} günün en düşüğünün "
            "ALTINA indiyse; (2) sitenin kendi listelemesinde üstü çizili eski fiyat "
            "varsa (geçmiş henüz yokken bile). "
            "Bir ürünün fiyat geçmişi grafiğini görmek için satırdaki 'Grafik' butonuna basın."
        )
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(
            "background: #fff7e0; border: 1px solid #f1d07a; "
            "padding: 8px; border-radius: 4px; color: #5a4a00;"
        )
        root.addWidget(self.banner)

        # Sekmeler
        self.tabs = QTabWidget()
        self.deal_table = DealTable("deals", db_path=self._db_path)
        self.all_table = DealTable("all", db_path=self._db_path)
        self.tabs.addTab(self.deal_table, "Fırsatlar (0)")
        self.tabs.addTab(self.all_table, "Tüm Ürünler (0)")
        root.addWidget(self.tabs, 1)

        # Alt durum çubuğu
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # belirsiz
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(10)
        root.addWidget(self.progress_bar)

        self.setCentralWidget(central)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Hazır. Taramak için butona basın.")

    # -- Persistence ----------------------------------------------------------
    def _load_last_snapshot(self) -> None:
        """DB'den en son 48 saatin ürün snapshot'ını yükleyip tablolara yaz.
        Böylece app her açılışta boş değil, son tarama sonuçlarıyla gelir."""
        try:
            db = PriceDatabase(self._db_path)
        except Exception:
            log.exception("DB açılamadı, snapshot yüklenemedi")
            return
        try:
            snapshot = db.latest_snapshot(hours=48)
            if not snapshot:
                return
            for listing, recorded_at in snapshot:
                self.all_table.add_product(listing)
                deal = detect_deal(
                    db,
                    listing,
                    window_days=self._config.history_days,
                    recorded_at=recorded_at,
                )
                if deal is not None:
                    self.deal_table.add_deal(deal)
            self._update_tab_counts()
            self._status.showMessage(
                f"Son tarama yüklendi: {len(snapshot)} ürün, "
                f"{self.deal_table.rowCount()} fırsat. Yenilemek için 'Taramayı Başlat'."
            )
        except Exception:
            log.exception("Snapshot yüklenirken hata")
        finally:
            db.close()

    # -- Events ---------------------------------------------------------------
    def _on_scan_clicked(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            # Çalışıyorsa iptal et
            self._status.showMessage("İptal ediliyor…")
            if self._worker:
                self._worker.cancel()
            return

        # Eski thread/worker varsa arşive al (silme — dangling ref crash'i).
        if self._thread is not None:
            self._old_threads.append(self._thread)
        if self._worker is not None:
            self._old_workers.append(self._worker)

        self.deal_table.clear_rows()
        self.all_table.clear_rows()
        self._errors.clear()
        self._skipped.clear()
        self._update_tab_counts()

        self.progress_bar.setVisible(True)
        self.scan_button.setText("İptal")
        self._status.showMessage("Tarama başlıyor…")

        self._thread, self._worker = start_scan_thread(self._config, self._db_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.product_found.connect(self._on_product)
        self._worker.deal_found.connect(self._on_deal)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)

    # Slotlar
    def _on_progress(self, msg: str) -> None:
        self._status.showMessage(f"Taranıyor: {msg}")

    def _on_product(self, listing: ProductListing) -> None:
        self.all_table.add_product(listing)
        self._update_tab_counts()

    def _on_deal(self, deal: Deal) -> None:
        self.deal_table.add_deal(deal)
        self._update_tab_counts()

    def _on_error(self, msg: str) -> None:
        """Hataları sessizce topla — tarama bitince tek seferde özet göster.
        Popup'ı tek tek açmak tarama akışını kesiyordu."""
        log.warning("Scan error: %s", msg)
        self._errors.append(msg)

    def _on_finished(self, summary: ScanSummary) -> None:
        log.info("_on_finished slot çalıştı (main thread)")
        self.progress_bar.setVisible(False)
        self.scan_button.setText("Taramayı Başlat")
        dur = ""
        if summary.finished_at:
            delta = summary.finished_at - summary.started_at
            dur = f" · {delta.total_seconds():.0f} sn"
        status_msg = (
            f"Tamamlandı: {summary.sites_scanned} site, "
            f"{summary.products_found} ürün, "
            f"{summary.deals_found} fırsat, "
            f"{len(summary.errors)} hata"
        )
        if summary.skipped:
            status_msg += f", {len(summary.skipped)} atlandı"
        status_msg += dur
        self._status.showMessage(status_msg)

        # ÖNEMLİ: self._thread ve self._worker'ı NONE YAPMA.
        # Python referansı düşerse Qt C++ objesi silinir, zaten quit etmek
        # üzere olan thread'in slot'ları dangling olur → crash.
        # Bir sonraki tarama başlarken bu ref'ler arşive taşınacak.

        self._show_completion_dialog(summary)

    def _show_completion_dialog(self, summary: ScanSummary) -> None:
        log.info("Özet dialog açılıyor")
        lines = [
            "✅ Tarama tamamlandı",
            "",
            f"• Site: {summary.sites_scanned}",
            f"• Ürün bulundu: {summary.products_found}",
            f"• Fırsat: {summary.deals_found}",
        ]
        if summary.skipped:
            lines.append(f"• Atlanan (bot koruması): {len(summary.skipped)}")
        if summary.errors:
            lines.append(f"• Hata: {len(summary.errors)}")
        if summary.finished_at:
            delta = summary.finished_at - summary.started_at
            lines.append(f"• Süre: {delta.total_seconds():.0f} sn")

        lines.append("")
        if summary.deals_found > 0:
            lines.append("Fırsatlar sekmesinde detayları görebilirsiniz.")
        elif summary.products_found > 0:
            lines.append(
                "Henüz fırsat yok (yeterli fiyat geçmişi birikmemiş). "
                "Birkaç gün üst üste tarayın; indirimler Fırsatlar sekmesinde görünecek."
            )
        else:
            lines.append("Hiç ürün bulunamadı. Log dosyasını inceleyin.")

        msg = QMessageBox(self)
        msg.setWindowTitle("Tarama Sonucu")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("\n".join(lines))

        detail_parts: list[str] = []
        if summary.skipped:
            detail_parts.append("Atlanan (bot koruması):\n" + "\n".join(summary.skipped))
        if summary.errors:
            detail_parts.append("Hatalar:\n" + "\n".join(summary.errors))
        if self.log_path:
            detail_parts.append(f"Log dosyası: {self.log_path}")
        if detail_parts:
            msg.setDetailedText("\n\n".join(detail_parts))

        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def _update_tab_counts(self) -> None:
        self.tabs.setTabText(0, f"Fırsatlar ({self.deal_table.rowCount()})")
        self.tabs.setTabText(1, f"Tüm Ürünler ({self.all_table.rowCount()})")

    # -- Close: arkaplan temizliği --------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread and self._thread.isRunning():
            if self._worker:
                self._worker.cancel()
            self._status.showMessage("Kapatılıyor…")
            # İptal işareti site/marka iterasyonlarının başında okunur;
            # Playwright'taki aktif istek bitene kadar küçük bir bekleme.
            if not self._thread.wait(20000):
                log.warning("ScanWorker zamanında durmadı, zorla sonlandırılıyor.")
                self._thread.terminate()
                self._thread.wait(2000)
        event.accept()

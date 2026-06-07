"""Tarama koordinatörü: tüm site × marka kombinasyonlarını dolaşır,
sonuçları DB'ye kaydeder, fırsatları UI'ya sinyalle bildirir.

QThread içinde asyncio event loop çalıştırır.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal

from src.core.config import AppConfig
from src.core.deal_detector import detect_deal
from src.core.models import Deal, ProductListing, ScanSummary
from src.scrapers.base import BaseScraper, BotProtectionError, ScraperError
from src.storage.db import PriceDatabase

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext


log = logging.getLogger(__name__)


SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {}


def register_default_scrapers() -> None:
    """Scraper sınıflarını registry'ye ekle. Lazy import çünkü Playwright
    henüz yüklenmemiş olabilir."""
    from src.scrapers.amazon_tr import AmazonTrScraper
    from src.scrapers.hepsiburada import HepsiburadaScraper
    from src.scrapers.trendyol import TrendyolScraper

    SCRAPER_REGISTRY["trendyol"] = TrendyolScraper
    SCRAPER_REGISTRY["hepsiburada"] = HepsiburadaScraper
    SCRAPER_REGISTRY["amazon_tr"] = AmazonTrScraper


class ScanWorker(QObject):
    """QThread içinde çalışan iş parçacığı. Sinyaller UI thread'ine gider."""

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
            register_default_scrapers()
        except Exception as exc:
            log.exception("Scraper kayıt hatası")
            msg = f"Scraper'lar yüklenemedi ({type(exc).__name__}): {exc}"
            self.error.emit(msg)
            self.finished.emit(ScanSummary(errors=[msg]))
            return

        try:
            asyncio.run(self._run_async())
        except Exception as exc:  # beklenmedik hata
            log.exception("ScanWorker crashed")
            msg = f"Tarama başarısız ({type(exc).__name__}): {exc}"
            self.error.emit(msg)
            self.finished.emit(ScanSummary(errors=[msg]))
        finally:
            log.info("ScanWorker.run() çıkıyor")

    async def _run_async(self) -> None:
        from playwright.async_api import async_playwright

        summary = ScanSummary()
        db = PriceDatabase(self._db_path)

        try:
            async with async_playwright() as pw:
                log.info("Chromium launching (headless=%s)", self._config.headless)
                browser = await pw.chromium.launch(
                    headless=self._config.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                log.info("Chromium launched")

                try:
                    for site_name in self._config.sites:
                        if self._cancelled:
                            break
                        scraper_cls = SCRAPER_REGISTRY.get(site_name)
                        if scraper_cls is None:
                            log.info("Scraper kayıtlı değil, atlanıyor: %s", site_name)
                            continue

                        # HER SİTE İÇİN AYRI CONTEXT — bir sitede bot
                        # korumasına düşünce (özellikle Hepsiburada) context
                        # kirleniyor, sonraki site geçişinde Playwright
                        # sessiz crash edebiliyordu. İzole edelim.
                        log.info("%s için yeni BrowserContext açılıyor", site_name)
                        context = await browser.new_context(
                            user_agent=(
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/131.0.0.0 Safari/537.36"
                            ),
                            locale="tr-TR",
                            timezone_id="Europe/Istanbul",
                            viewport={"width": 1366, "height": 900},
                        )
                        await context.add_init_script(
                            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                            "Object.defineProperty(navigator,'languages',{get:()=>['tr-TR','tr','en']});"
                        )
                        summary.sites_scanned += 1

                        scraper = scraper_cls(
                            context,
                            max_products=self._config.max_products_per_brand_per_site,
                            request_delay_ms=self._config.request_delay_ms,
                            search_suffix=self._config.search_suffix,
                            product_types=self._config.product_types,
                        )

                        # Bir sitede ilk markada bot koruması alındıysa
                        # kalan markaları denememeye gerek yok (hepsi aynı
                        # korumaya takılacak).
                        site_bot_blocked = False

                        try:
                            for brand in self._config.brands:
                                if self._cancelled:
                                    break
                                summary.brands_scanned += 1
                                self.progress.emit(f"{site_name.title()} · {brand}")

                                if site_bot_blocked:
                                    msg = f"{site_name}/{brand}: (site bloklu, atlandı)"
                                    summary.skipped.append(msg)
                                    continue

                                try:
                                    listings = await scraper.search(brand)
                                except BotProtectionError as exc:
                                    msg = f"{site_name}/{brand}: bot koruması ({exc})"
                                    log.info(msg)
                                    summary.skipped.append(msg)
                                    self.progress.emit(
                                        f"{site_name.title()} · bot koruması nedeniyle atlanıyor"
                                    )
                                    site_bot_blocked = True
                                    continue
                                except ScraperError as exc:
                                    msg = f"{site_name}/{brand}: {exc}"
                                    log.warning(msg)
                                    summary.errors.append(msg)
                                    self.error.emit(msg)
                                    continue
                                except Exception as exc:
                                    msg = f"{site_name}/{brand}: beklenmedik hata — {exc}"
                                    log.exception(msg)
                                    summary.errors.append(msg)
                                    self.error.emit(msg)
                                    continue

                                for listing in listings:
                                    summary.products_found += 1
                                    recorded_at = db.record_listing(listing)
                                    self.product_found.emit(listing)

                                    deal = detect_deal(
                                        db,
                                        listing,
                                        window_days=self._config.history_days,
                                        recorded_at=recorded_at,
                                    )
                                    if deal is not None:
                                        summary.deals_found += 1
                                        self.deal_found.emit(deal)
                        finally:
                            log.info("%s context kapatılıyor", site_name)
                            try:
                                await context.close()
                            except Exception:
                                log.exception("%s context.close() hata", site_name)
                finally:
                    log.info("Chromium kapatılıyor")
                    try:
                        await browser.close()
                    except Exception:
                        log.exception("browser.close() hata")
        finally:
            db.close()
            log.info("DB kapatıldı")

        from datetime import datetime as _dt
        summary.finished_at = _dt.now()
        log.info(
            "Tarama tamam: %d site, %d ürün, %d fırsat, %d hata, %d atlandı",
            summary.sites_scanned,
            summary.products_found,
            summary.deals_found,
            len(summary.errors),
            len(summary.skipped),
        )
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

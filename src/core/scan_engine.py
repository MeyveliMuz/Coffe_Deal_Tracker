"""Framework-bağımsız tarama çekirdeği.

Hiçbir UI/framework'e (Qt, FastAPI...) bağlı DEĞİL. Tarama olaylarını
callback'lerle bildirir ve bittiğinde bir `ScanSummary` döndürür. Böylece:

  - Qt worker'ı (`src/core/scanner.py`) callback'leri Qt sinyallerine,
  - FastAPI backend'i callback'leri WebSocket mesajlarına

çevirerek aynı çekirdeği paylaşır. Tarama mantığı (site × marka döngüsü,
bot koruma toleransı, izole context'ler) tek yerde tutulur.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Optional

from src.core.config import AppConfig
from src.core.deal_detector import detect_deal
from src.core.models import Deal, ProductListing, ScanSummary
from src.scrapers.base import BaseScraper, BotProtectionError, ScraperError
from src.storage.db import PriceDatabase

if TYPE_CHECKING:  # yalnızca tip ipuçları — çalışma zamanında Playwright import edilmez
    from playwright.async_api import BrowserContext  # noqa: F401


log = logging.getLogger(__name__)


SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {}


def register_default_scrapers() -> None:
    """Scraper sınıflarını registry'ye ekle. Lazy import çünkü Playwright
    henüz yüklenmemiş olabilir. İdempotent — birden fazla çağrı zararsız."""
    from src.scrapers.amazon_tr import AmazonTrScraper
    from src.scrapers.hepsiburada import HepsiburadaScraper
    from src.scrapers.trendyol import TrendyolScraper

    SCRAPER_REGISTRY["trendyol"] = TrendyolScraper
    SCRAPER_REGISTRY["hepsiburada"] = HepsiburadaScraper
    SCRAPER_REGISTRY["amazon_tr"] = AmazonTrScraper


# Callback tipleri (hepsi opsiyonel)
ProgressCb = Callable[[str], None]
ProductCb = Callable[[ProductListing], None]
DealCb = Callable[[Deal], None]
ErrorCb = Callable[[str], None]
CancelCb = Callable[[], bool]

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_INIT_SCRIPT = (
    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    "Object.defineProperty(navigator,'languages',{get:()=>['tr-TR','tr','en']});"
)


def _safe(cb, *args) -> None:
    """Callback'i çağır; callback içindeki bir hata taramayı çökertmesin."""
    if cb is None:
        return
    try:
        cb(*args)
    except Exception:
        log.exception("Tarama callback hatası (yok sayıldı)")


async def run_scan(
    config: AppConfig,
    db_path: str,
    *,
    on_progress: Optional[ProgressCb] = None,
    on_product: Optional[ProductCb] = None,
    on_deal: Optional[DealCb] = None,
    on_error: Optional[ErrorCb] = None,
    should_cancel: Optional[CancelCb] = None,
) -> ScanSummary:
    """Tüm site × marka kombinasyonlarını tarar, sonuçları DB'ye yazar,
    olayları callback'lerle bildirir ve bir `ScanSummary` döndürür.

    Üst düzey hatalar (scraper yükleme, beklenmedik çökme) yakalanır;
    fonksiyon istisna FIRLATMAZ — her durumda summary döner.
    """
    summary = ScanSummary()
    cancelled: CancelCb = should_cancel or (lambda: False)

    # Scraper'ları yükle (Playwright eksikse hata burada çıkar)
    try:
        register_default_scrapers()
    except Exception as exc:
        log.exception("Scraper kayıt hatası")
        msg = f"Scraper'lar yüklenemedi ({type(exc).__name__}): {exc}"
        _safe(on_error, msg)
        summary.errors.append(msg)
        summary.finished_at = datetime.now()
        return summary

    try:
        await _scan(config, db_path, summary, on_progress, on_product, on_deal, on_error, cancelled)
    except Exception as exc:  # beklenmedik hata
        log.exception("Tarama beklenmedik şekilde çöktü")
        msg = f"Tarama başarısız ({type(exc).__name__}): {exc}"
        _safe(on_error, msg)
        summary.errors.append(msg)

    summary.finished_at = datetime.now()
    log.info(
        "Tarama tamam: %d site, %d ürün, %d fırsat, %d hata, %d atlandı",
        summary.sites_scanned,
        summary.products_found,
        summary.deals_found,
        len(summary.errors),
        len(summary.skipped),
    )
    return summary


async def _scan(
    config: AppConfig,
    db_path: str,
    summary: ScanSummary,
    on_progress: Optional[ProgressCb],
    on_product: Optional[ProductCb],
    on_deal: Optional[DealCb],
    on_error: Optional[ErrorCb],
    cancelled: CancelCb,
) -> None:
    """Asıl tarama döngüsü. Playwright'ı burada (lazy) import ederiz."""
    from playwright.async_api import async_playwright

    db = PriceDatabase(db_path)
    try:
        async with async_playwright() as pw:
            log.info("Chromium launching (headless=%s)", config.headless)
            browser = await pw.chromium.launch(
                headless=config.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            log.info("Chromium launched")

            try:
                for site_name in config.sites:
                    if cancelled():
                        break
                    scraper_cls = SCRAPER_REGISTRY.get(site_name)
                    if scraper_cls is None:
                        log.info("Scraper kayıtlı değil, atlanıyor: %s", site_name)
                        continue

                    # HER SİTE İÇİN AYRI CONTEXT — bir sitede bot korumasına
                    # düşünce (özellikle Hepsiburada) context kirleniyor,
                    # sonraki site geçişinde Playwright sessiz crash
                    # edebiliyordu. İzole edelim.
                    log.info("%s için yeni BrowserContext açılıyor", site_name)
                    context = await browser.new_context(
                        user_agent=_UA,
                        locale="tr-TR",
                        timezone_id="Europe/Istanbul",
                        viewport={"width": 1366, "height": 900},
                    )
                    await context.add_init_script(_INIT_SCRIPT)
                    summary.sites_scanned += 1

                    scraper = scraper_cls(
                        context,
                        max_products=config.max_products_per_brand_per_site,
                        request_delay_ms=config.request_delay_ms,
                        search_suffix=config.search_suffix,
                        product_types=config.product_types,
                    )

                    # Bir sitede ilk markada bot koruması alındıysa kalan
                    # markaları denememeye gerek yok (hepsi aynı korumaya takılır).
                    site_bot_blocked = False

                    try:
                        for brand in config.brands:
                            if cancelled():
                                break
                            summary.brands_scanned += 1
                            _safe(on_progress, f"{site_name.title()} · {brand}")

                            if site_bot_blocked:
                                summary.skipped.append(
                                    f"{site_name}/{brand}: (site bloklu, atlandı)"
                                )
                                continue

                            try:
                                listings = await scraper.search(brand)
                            except BotProtectionError as exc:
                                msg = f"{site_name}/{brand}: bot koruması ({exc})"
                                log.info(msg)
                                summary.skipped.append(msg)
                                _safe(
                                    on_progress,
                                    f"{site_name.title()} · bot koruması nedeniyle atlanıyor",
                                )
                                site_bot_blocked = True
                                continue
                            except ScraperError as exc:
                                msg = f"{site_name}/{brand}: {exc}"
                                log.warning(msg)
                                summary.errors.append(msg)
                                _safe(on_error, msg)
                                continue
                            except Exception as exc:
                                msg = f"{site_name}/{brand}: beklenmedik hata — {exc}"
                                log.exception(msg)
                                summary.errors.append(msg)
                                _safe(on_error, msg)
                                continue

                            for listing in listings:
                                summary.products_found += 1
                                recorded_at = db.record_listing(listing)
                                _safe(on_product, listing)

                                deal = detect_deal(
                                    db,
                                    listing,
                                    window_days=config.history_days,
                                    recorded_at=recorded_at,
                                )
                                if deal is not None:
                                    summary.deals_found += 1
                                    _safe(on_deal, deal)
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

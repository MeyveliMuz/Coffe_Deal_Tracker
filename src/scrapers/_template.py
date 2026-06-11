"""YENİ SİTE SCRAPER ŞABLONU — kopyalayıp doldurun.

Yeni bir site eklemek için:
  1. Bu dosyayı `src/scrapers/<site>.py` olarak kopyalayın.
  2. `site_name`, `BASE` ve `search()` içindeki seçicileri o sitenin canlı
     HTML'ine göre doldurun (tarayıcıda DevTools ile inceleyin).
  3. `src/core/scan_engine.py` → `register_default_scrapers()` içine ekleyin:
         from src.scrapers.<site> import <Site>Scraper
         SCRAPER_REGISTRY["<site>"] = <Site>Scraper
  4. `config.json` → `sites` listesine `"<site>"` ekleyin.

NOT: Seçiciler siteye özgüdür ve site HTML'ini değiştirdiğinde kırılır —
bu yüzden dosyanın başına "son doğrulama" tarihi yazın (diğer scraper'lar gibi).

Mimari sayesinde çekirdek (scan_engine, deal_detector, db, UI) HİÇ
değişmez — yalnızca bu dosyayı eklersiniz.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import TYPE_CHECKING

from src.core.models import ProductListing
from src.scrapers.base import BaseScraper, BotProtectionError, ScraperError

if TYPE_CHECKING:
    from playwright.async_api import Page  # noqa: F401

log = logging.getLogger(__name__)


class TemplateScraper(BaseScraper):
    site_name = "template"          # TODO: ör. "n11"
    BASE = "https://www.example.com"  # TODO: sitenin kök adresi

    async def search(self, brand: str) -> list[ProductListing]:
        query = self._build_query(brand)
        url = f"{self.BASE}/ara?q={urllib.parse.quote_plus(query)}"  # TODO: arama URL şablonu

        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)

            # TODO: bot koruması / CAPTCHA tespiti — gerekirse:
            # if "captcha" in (await page.content()).lower():
            #     raise BotProtectionError(f"{self.site_name} CAPTCHA")

            card_selector = ".product-card"  # TODO: ürün kartı seçicisi
            try:
                await page.wait_for_selector(card_selector, timeout=15000)
            except Exception:
                log.warning("%s: sonuç bulunamadı (%s)", self.site_name, query)
                return []

            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(600)

            cards = await page.query_selector_all(card_selector)
            results: list[ProductListing] = []
            for card in cards:
                if len(results) >= self.max_products:
                    break
                listing = await self._parse_card(card, brand)
                if listing is None:
                    continue
                if not self._brand_matches(listing.name, brand):
                    continue
                if not self._product_allowed(listing.name):  # ürün türü filtresi (ortak)
                    continue
                results.append(listing)
            return results
        finally:
            await page.close()
            await self._polite_wait()

    async def _parse_card(self, card, brand: str) -> ProductListing | None:
        try:
            # TODO: bu dört alanı siteye göre çıkarın
            link_el = await card.query_selector("a[href]")
            href = await link_el.get_attribute("href") if link_el else None
            if not href:
                return None
            if href.startswith("/"):
                href = self.BASE + href

            name_el = await card.query_selector(".product-name")
            name = (await name_el.inner_text()).strip() if name_el else ""
            if not name:
                return None

            price_el = await card.query_selector(".price")
            price = self._parse_price_tr((await price_el.inner_text()).strip()) if price_el else None
            if price is None or price <= 0:
                return None

            # İndirimli (üstü çizili) eski fiyat — varsa site-bazlı fırsat tespiti için
            original_price: float | None = None
            old_el = await card.query_selector("del, .old-price")
            if old_el is not None:
                old_val = self._parse_price_tr((await old_el.inner_text()).strip())
                if old_val is not None and old_val > price:
                    original_price = old_val

            img_el = await card.query_selector("img")
            image_url = await img_el.get_attribute("src") if img_el else None

            return ProductListing(
                url=href.split("?")[0],
                name=name,
                price=price,
                site=self.site_name,
                brand=brand.lower(),
                image_url=image_url,
                original_price=original_price,
            )
        except Exception as exc:
            log.debug("%s kart parse hatası: %s", self.site_name, exc)
            return None

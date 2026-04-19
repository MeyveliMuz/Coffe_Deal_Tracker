"""Amazon.com.tr scraper.

Son doğrulama: 2026-04-18
URL şablonu: https://www.amazon.com.tr/s?k=<query>
Her ürün kartı `div[data-asin]` öğesidir; ürün URL'i ASIN'den üretilir.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import TYPE_CHECKING

from src.core.models import ProductListing
from src.scrapers.base import BaseScraper, BotProtectionError, ScraperError

if TYPE_CHECKING:
    from playwright.async_api import Page


log = logging.getLogger(__name__)


CAPTCHA_KEYWORDS = [
    "robot",
    "captcha",
    "automated access",
    "enter the characters",
    "doğrulama",  # Amazon TR
]


class AmazonTrScraper(BaseScraper):
    site_name = "amazon_tr"
    BASE = "https://www.amazon.com.tr"

    async def search(self, brand: str) -> list[ProductListing]:
        query = self._build_query(brand)
        url = f"{self.BASE}/s?k={urllib.parse.quote_plus(query)}"

        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)

            # CAPTCHA kontrolü — title veya içerikte
            title = (await page.title()).lower()
            body_text = (await page.locator("body").inner_text()).lower()[:2000]
            if any(k in title or k in body_text for k in CAPTCHA_KEYWORDS):
                if "sonuç" not in title:  # "sonuçları" normal listeyi işaret eder
                    raise BotProtectionError("Amazon CAPTCHA / bot koruması")

            try:
                await page.wait_for_selector("div[data-asin]", timeout=15000)
            except Exception:
                log.warning("Amazon: ürün bulunamadı (%s)", query)
                return []

            await page.wait_for_timeout(800)

            cards = await page.query_selector_all("div[data-asin]")
            results: list[ProductListing] = []
            for card in cards:
                if len(results) >= self.max_products:
                    break
                listing = await self._parse_card(card, brand)
                if listing is None:
                    continue
                if not self._brand_matches(listing.name, brand):
                    continue
                results.append(listing)
            return results
        finally:
            await page.close()
            await self._polite_wait()

    async def _parse_card(self, card, brand: str) -> ProductListing | None:
        try:
            asin = await card.get_attribute("data-asin")
            if not asin or not asin.strip():
                return None

            # Başlık
            title_el = (
                await card.query_selector("h2 a span")
                or await card.query_selector("h2 span")
                or await card.query_selector("[data-cy='title-recipe'] span")
            )
            title = (await title_el.inner_text()).strip() if title_el else ""
            if not title:
                return None

            # Fiyat — ".a-offscreen" tam fiyatı içerir (ör. "725,00 TL")
            price_el = await card.query_selector(".a-price .a-offscreen")
            price_txt = (await price_el.inner_text()).strip() if price_el else ""
            price = self._parse_price_tr(price_txt)
            if price is None or price <= 0:
                return None

            # Resim
            img_el = await card.query_selector("img.s-image")
            image_url = await img_el.get_attribute("src") if img_el else None

            # URL: ASIN'den standart ürün sayfası
            url = f"{self.BASE}/dp/{asin}"

            return ProductListing(
                url=url,
                name=title,
                price=price,
                site=self.site_name,
                brand=brand.lower(),
                image_url=image_url,
            )
        except Exception as exc:
            log.debug("Amazon kart parse hatası: %s", exc)
            return None


# Manuel test: python -m src.scrapers.amazon_tr meinl
if __name__ == "__main__":
    import asyncio
    import sys

    async def _main() -> None:
        from playwright.async_api import async_playwright

        brand = sys.argv[1] if len(sys.argv) > 1 else "meinl"
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="tr-TR",
            )
            scraper = AmazonTrScraper(ctx, max_products=10, request_delay_ms=500)
            try:
                results = await scraper.search(brand)
            except ScraperError as exc:
                print(f"HATA: {exc}")
                results = []
            for r in results:
                print(f"{r.price:>8.2f} TL  {r.name[:70]}")
                print(f"          {r.url}")
            print(f"\nToplam: {len(results)} ürün")
            await browser.close()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(_main())

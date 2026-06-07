"""Hepsiburada scraper.

Son doğrulama: 2026-04-18

⚠ ÖNEMLİ: Hepsiburada agresif bot koruması uyguluyor ("Güvenlik" sayfası).
Headless mode genellikle bloklanıyor. Gerçek kullanıcı makinesinde headful
modda + gerçekçi UA ile bazen geçiyor. Blok tespit edilirse BotProtectionError
fırlatılır; uygulama bunu hata olarak raporlar ve diğer sitelerle devam eder.

URL şablonu: https://www.hepsiburada.com/ara?q=<query>
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


class HepsiburadaScraper(BaseScraper):
    site_name = "hepsiburada"
    BASE = "https://www.hepsiburada.com"

    async def search(self, brand: str) -> list[ProductListing]:
        query = self._build_query(brand)
        url = f"{self.BASE}/ara?q={urllib.parse.quote_plus(query)}"

        page = await self.context.new_page()
        try:
            # Warm-up: önce ana sayfayı ziyaret et — çerezler set olsun,
            # referer gerçekçi görünsün. Doğrudan search URL'ine gitmek
            # daha hızlı bot tespiti tetikliyor.
            try:
                await page.goto(self.BASE + "/", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(1200)
            except Exception:
                pass  # warm-up zorunlu değil, asıl URL'ye geç

            await page.goto(url, wait_until="domcontentloaded", timeout=45000)

            # Güvenlik sayfası kontrolü — başlık + URL + body
            title = (await page.title()).lower()
            current_url = page.url.lower()
            body_snippet = ""
            try:
                body_snippet = (await page.inner_text("body", timeout=2000))[:500].lower()
            except Exception:
                pass
            if (
                "güvenlik" in title
                or "security" in title
                or "guvenlik" in current_url
                or "robot" in body_snippet
                or "güvenlik doğrulaması" in body_snippet
            ):
                raise BotProtectionError(
                    "Hepsiburada güvenlik sayfası gösteriyor (bot koruması). "
                    "config.json'da `headless: false` deneyin."
                )

            # Ürün kartları için birden fazla olası seçici dene
            product_sel = (
                "li.productListContent-item, "
                "[data-test-id='product-card'], "
                "li[class*='productCard']"
            )

            try:
                await page.wait_for_selector(product_sel, timeout=15000)
            except Exception:
                log.warning("Hepsiburada: sonuç bulunamadı (%s)", query)
                return []

            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(800)

            cards = await page.query_selector_all(product_sel)
            results: list[ProductListing] = []
            for card in cards:
                if len(results) >= self.max_products:
                    break
                listing = await self._parse_card(card, brand)
                if listing is None:
                    continue
                if not self._brand_matches(listing.name, brand):
                    continue
                if not self._product_allowed(listing.name):
                    continue
                results.append(listing)

            return results
        finally:
            await page.close()
            await self._polite_wait()

    async def _parse_card(self, card, brand: str) -> ProductListing | None:
        try:
            # Link (ya <a> içinde ya da <a> kartın kendisi)
            link_el = await card.query_selector("a[href]")
            href = await link_el.get_attribute("href") if link_el else None
            if not href:
                return None
            if href.startswith("/"):
                href = self.BASE + href

            # İsim — birkaç olası seçici
            title_el = (
                await card.query_selector("h3[data-test-id='product-card-name']")
                or await card.query_selector("h3")
                or await card.query_selector("[title]")
            )
            if title_el is None:
                return None
            title = (await title_el.inner_text()).strip()
            if not title:
                # Fallback: title attribute
                t2 = await card.get_attribute("title")
                if t2:
                    title = t2.strip()
            if not title:
                return None

            # Fiyat
            price_el = (
                await card.query_selector("[data-test-id='price-current-price']")
                or await card.query_selector("div[class*='price']")
                or await card.query_selector("span[class*='price']")
            )
            price_txt = (await price_el.inner_text()).strip() if price_el else ""
            price = self._parse_price_tr(price_txt)
            if price is None or price <= 0:
                return None

            # Üstü çizili / önceki fiyat
            original_price: float | None = None
            old_el = (
                await card.query_selector("[data-test-id='price-prev-price']")
                or await card.query_selector("div[class*='prevPrice']")
                or await card.query_selector("span[class*='prevPrice']")
                or await card.query_selector("del")
            )
            if old_el is not None:
                old_txt = (await old_el.inner_text()).strip()
                old_val = self._parse_price_tr(old_txt)
                if old_val is not None and old_val > price:
                    original_price = old_val

            # Resim
            img_el = await card.query_selector("img")
            image_url = None
            if img_el:
                image_url = (
                    await img_el.get_attribute("src")
                    or await img_el.get_attribute("data-src")
                )

            return ProductListing(
                url=href.split("?")[0],
                name=title,
                price=price,
                site=self.site_name,
                brand=brand.lower(),
                image_url=image_url,
                original_price=original_price,
            )
        except Exception as exc:
            log.debug("Hepsiburada kart parse hatası: %s", exc)
            return None


# Manuel test: python -m src.scrapers.hepsiburada meinl
if __name__ == "__main__":
    import asyncio
    import sys

    async def _main() -> None:
        from playwright.async_api import async_playwright

        brand = sys.argv[1] if len(sys.argv) > 1 else "meinl"
        async with async_playwright() as pw:
            # Headful deneyin — bot korumasını geçmek daha kolay
            browser = await pw.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="tr-TR",
                timezone_id="Europe/Istanbul",
            )
            await ctx.add_init_script(
                'Object.defineProperty(navigator,"webdriver",{get:()=>undefined});'
            )
            scraper = HepsiburadaScraper(ctx, max_products=10, request_delay_ms=500)
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

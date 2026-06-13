"""Hepsiburada scraper.

Son doğrulama: 2026-06-14

⚠ ÖNEMLİ: Hepsiburada agresif bot koruması uyguluyor ("Güvenlik" sayfası).
Headless mode genellikle bloklanıyor. Gerçek kullanıcı makinesinde headful
modda + gerçekçi UA ile bazen geçiyor. Blok tespit edilirse BotProtectionError
fırlatılır; uygulama bunu hata olarak raporlar ve diğer sitelerle devam eder.

URL şablonu: https://www.hepsiburada.com/ara?q=<query>

Arama sonuç sayfası CSS-module ile (karmalı sınıf adları) render ediliyor.
Sabit tutamaçlar: ürün kartları `<li>` içinde `data-test-id="title-N"` ve
`final-price-N` (N = 1'den artan indeks). Üstü çizili fiyat sınıf adında
"originalPrice", ürün linki "productCardLink" içerir. Karttan veriyi tek bir
`page.evaluate` çağrısıyla (ham sözlük) çekip Python tarafında filtreliyoruz —
karmalı sınıf son eklerine bağımlı kalmamak için.
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

            # Ürün kartları yüklendi mi? Kartlar `data-test-id="title-N"` taşır.
            try:
                await page.wait_for_selector(
                    "[data-test-id^='title-']", timeout=15000
                )
            except Exception:
                log.warning("Hepsiburada: sonuç bulunamadı (%s)", query)
                return []

            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(800)

            raw_cards = await self._extract_cards(page)
            results: list[ProductListing] = []
            for raw in raw_cards:
                if len(results) >= self.max_products:
                    break
                listing = self._build_listing(raw, brand)
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

    async def _extract_cards(self, page: "Page") -> list[dict]:
        """Sonuç sayfasındaki ürün kartlarından ham veriyi tek seferde çek.

        Sınıf adları CSS-module ile karmalı (ör. `price-module_originalPrice__43Wnd`)
        olduğundan sabit ekleri (`data-test-id`, sınıf adı parçaları) kullanırız.
        """
        return await page.evaluate(
            """() => {
                const cards = [...document.querySelectorAll('li')]
                    .filter(li => li.querySelector('[data-test-id^="title-"]'));
                return cards.map(card => {
                    const titleEl = card.querySelector('[data-test-id^="title-"]');
                    const linkEl =
                        card.querySelector('a[class*="productCardLink"]') ||
                        card.querySelector('a[href]');
                    const priceEl = card.querySelector('[data-test-id^="final-price-"]');
                    // DİKKAT: iki sınıf eşleşir — `originalPriceArea` (fiyat +
                    // "%15" indirim rozetini birlikte içerir → parse'ta 735+15=73515
                    // gibi saçma değer) ve `originalPrice` (yalnız fiyat). `__`
                    // ayıracı (CSS-module name__hash) sadece doğru olanı seçer.
                    const oldEl = card.querySelector('[class*="originalPrice__"]');
                    const imgEl = card.querySelector('img');
                    const name = titleEl
                        ? (titleEl.innerText || titleEl.getAttribute('title') || '').trim()
                        : '';
                    return {
                        name,
                        href: linkEl ? linkEl.getAttribute('href') : null,
                        priceText: priceEl ? priceEl.innerText.trim() : '',
                        oldPriceText: oldEl ? oldEl.innerText.trim() : '',
                        imageUrl: imgEl
                            ? (imgEl.getAttribute('src') || imgEl.getAttribute('data-src'))
                            : null,
                    };
                });
            }"""
        )

    def _build_listing(self, raw: dict, brand: str) -> ProductListing | None:
        try:
            href = raw.get("href")
            name = (raw.get("name") or "").strip()
            if not href or not name:
                return None
            if href.startswith("/"):
                href = self.BASE + href

            price = self._parse_price_tr(raw.get("priceText", ""))
            if price is None or price <= 0:
                return None

            original_price: float | None = None
            old_val = self._parse_price_tr(raw.get("oldPriceText", ""))
            if old_val is not None and old_val > price:
                original_price = old_val

            return ProductListing(
                url=href.split("?")[0],
                name=name,
                price=price,
                site=self.site_name,
                brand=brand.lower(),
                image_url=raw.get("imageUrl"),
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

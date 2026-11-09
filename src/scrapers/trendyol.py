"""Trendyol scraper.

Son doğrulama: 2026-11-09
URL şablonu: https://www.trendyol.com/sr?q=<query>
Selector kırılırsa bu dosyanın üstündeki tarihi güncelleyin.
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


class TrendyolScraper(BaseScraper):
    site_name = "trendyol"
    BASE = "https://www.trendyol.com"

    async def search(self, brand: str) -> list[ProductListing]:
        query = self._build_query(brand)
        url = f"{self.BASE}/sr?q={urllib.parse.quote_plus(query)}"

        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await self._dismiss_popups(page)

            # Ana ürün listesi container'ı yüklensin
            try:
                await page.wait_for_selector(".product-card", timeout=20000)
            except Exception as exc:
                # İçerik gelmediyse bot koruması veya sonuç yok
                if "captcha" in (await page.content()).lower():
                    raise BotProtectionError("Trendyol CAPTCHA") from exc
                log.warning("Trendyol: sonuç bulunamadı (%s)", query)
                return []

            # Biraz aşağı scroll ederek lazy-load kartları tetikle
            await page.evaluate("window.scrollBy(0, 1200)")
            await page.wait_for_timeout(800)

            raw_cards = await self._extract_cards(page)
            results: list[ProductListing] = []
            seen: set[str] = set()
            for raw in raw_cards:
                if len(results) >= self.max_products:
                    break
                listing = self._build_listing(raw, brand)
                if listing is None or listing.url in seen:
                    continue
                if not self._brand_matches(listing.name, brand):
                    continue
                if not self._product_allowed(listing.name):
                    continue
                seen.add(listing.url)
                results.append(listing)

            return results
        finally:
            await page.close()
            await self._polite_wait()

    # ------------------------------------------------------------------
    async def _dismiss_popups(self, page: "Page") -> None:
        """Çerez / login popup'larını kapat."""
        for sel in [
            "#onetrust-accept-btn-handler",
            "button:has-text('Tümünü Kabul Et')",
            ".modal-close",
            "button[aria-label='Kapat']",
        ]:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click(timeout=2000)
                    await page.wait_for_timeout(300)
            except Exception:
                pass

    async def _extract_cards(self, page: "Page") -> list[dict]:
        """Tüm kartların ham verisini TEK tarayıcı çağrısında (atomik) oku.

        Eskiden her alan ayrı bir await ile okunuyordu (href → ad → fiyat).
        Trendyol listeyi o arada yeniden çizerse (lazy-load / reklam kartı)
        aynı DOM düğümü başka ürünü gösteriyor, ad bir üründen fiyat komşusundan
        geliyordu (2026-11-09: 1.580 TL'lik 1 kg paket, yanındaki 500 g'lık
        ürünün 783,02 TL fiyatıyla kaydedildi → sahte %50 indirim).
        """
        return await page.evaluate(
            """() => [...document.querySelectorAll('.product-card')].map(c => {
                const t = s => { const e = c.querySelector(s); return e ? e.innerText.trim() : ''; };
                const img = c.querySelector("img[data-testid='image-img'], img");
                return {
                    href: c.getAttribute('href'),
                    brand: t('.product-brand'),
                    name: t('.product-name'),
                    alt: img ? (img.getAttribute('alt') || '') : '',
                    discounted: t('.discounted-price, .sale-price'),
                    strike: t('.strikethrough-price'),
                    single: t('.single-price'),
                    section: t('.price-section'),
                    image: img ? (img.getAttribute('src') || img.getAttribute('data-src')) : null,
                };
            })"""
        )

    def _build_listing(self, raw: dict, brand: str) -> ProductListing | None:
        href = raw.get("href")
        if not href:
            return None
        if href.startswith("/"):
            href = self.BASE + href

        # Ad: marka + ürün adı iki ayrı span; yoksa resmin alt metni
        full_name = f"{raw.get('brand', '')} {raw.get('name', '')}".strip() or raw.get("alt", "").strip()
        if not full_name:
            return None

        # Fiyat — indirimli kartta .discounted-price aktif fiyat,
        # .strikethrough-price üstü çizili eski fiyat; indirimsizde .single-price.
        original_price: float | None = None
        if raw.get("discounted"):
            price = self._pick_lowest_price(raw["discounted"])
            if raw.get("strike"):
                original_price = self._pick_lowest_price(raw["strike"])
        elif raw.get("single"):
            price = self._pick_lowest_price(raw["single"])
        else:
            price = self._pick_lowest_price(raw.get("section", ""))

        if price is None or price <= 0:
            return None
        # Eski fiyat yeni fiyattan düşük/eşitse gerçek bir indirim yok, temizle.
        if original_price is not None and original_price <= price:
            original_price = None

        return ProductListing(
            url=href.split("?")[0],  # query param'ları temizle
            name=full_name,
            price=price,
            site=self.site_name,
            brand=brand.lower(),
            image_url=raw.get("image"),
            original_price=original_price,
        )

    @staticmethod
    def _pick_lowest_price(text: str) -> float | None:
        """Fiyat metninden gerçek satış fiyatını çıkar.

        Trendyol ürün kartı bazen birden fazla fiyat gösterir:
          - üstü çizili eski fiyat + indirimli yeni fiyat
          - kapsül/paket ürünlerinde "329 TL  (32,90 TL / Adet)" gibi birim fiyat

        Önce "/ Adet", "/ kg" gibi birim fiyatlarını eleriz, sonra kalanların
        en düşüğünü döndürürüz (indirimli fiyat genelde düşük olandır).
        """
        import re

        # "/ Adet", "/ kg", "/ ml" vb. ile biten ifadeleri kaldır
        cleaned_text = re.sub(
            r"[\d.,]+\s*TL\s*/\s*\w+",
            " ",
            text,
            flags=re.IGNORECASE,
        )

        candidates: list[float] = []
        for match in re.findall(r"[\d.,]+\s*TL", cleaned_text):
            val = BaseScraper._parse_price_tr(match)
            if val is not None and val > 0:
                candidates.append(val)
        if candidates:
            return min(candidates)
        return BaseScraper._parse_price_tr(cleaned_text)


# Manuel test entry point: python -m src.scrapers.trendyol meinl
if __name__ == "__main__":
    import asyncio
    import sys

    async def _main() -> None:
        from playwright.async_api import async_playwright

        brand = sys.argv[1] if len(sys.argv) > 1 else "meinl"
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False)
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="tr-TR",
            )
            scraper = TrendyolScraper(ctx, max_products=10, request_delay_ms=500)
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

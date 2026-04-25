"""Trendyol scraper.

Son doğrulama: 2026-04-18
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

            cards = await page.query_selector_all(".product-card")
            results: list[ProductListing] = []
            for card in cards:
                if len(results) >= self.max_products:
                    break
                listing = await self._parse_card(card, brand)
                if listing is None:
                    continue
                if not self._brand_matches(listing.name, brand):
                    continue
                if not self._is_whole_bean(listing.name):
                    continue
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

    async def _parse_card(self, card, brand: str) -> ProductListing | None:
        try:
            # Kart <a> elementinin kendisi; href doğrudan burada
            href = await card.get_attribute("href")
            if not href:
                return None
            if href.startswith("/"):
                href = self.BASE + href

            # Ad: marka + ürün adı iki ayrı span
            brand_el = await card.query_selector(".product-brand")
            name_el = await card.query_selector(".product-name")
            brand_txt = (await brand_el.inner_text()).strip() if brand_el else ""
            name_txt = (await name_el.inner_text()).strip() if name_el else ""
            full_name = f"{brand_txt} {name_txt}".strip()

            if not full_name:
                # Fallback: resmin alt attribute'u genellikle tam adı içerir
                img_el = await card.query_selector("img[data-testid='image-img']")
                if img_el:
                    alt = await img_el.get_attribute("alt")
                    if alt:
                        full_name = alt.strip()
            if not full_name:
                return None

            # Fiyat — .single-price indirimsiz tek fiyat; indirimli varyantlarda
            # .discounted-price aktif fiyat, .strikethrough-price üstü çizili
            # eski fiyat. Önce her ikisini ayrı ayrı yakalamayı dene; olmazsa
            # eski fallback'e (price-section bütünü) düş.
            discounted_el = await card.query_selector(".discounted-price, .sale-price")
            strikethrough_el = await card.query_selector(".strikethrough-price")
            single_el = await card.query_selector(".single-price")

            price: float | None = None
            original_price: float | None = None

            if discounted_el is not None:
                price = self._pick_lowest_price(
                    (await discounted_el.inner_text()).strip()
                )
                if strikethrough_el is not None:
                    original_price = self._pick_lowest_price(
                        (await strikethrough_el.inner_text()).strip()
                    )
            elif single_el is not None:
                price = self._pick_lowest_price(
                    (await single_el.inner_text()).strip()
                )
            else:
                section_el = await card.query_selector(".price-section")
                price_txt = (await section_el.inner_text()).strip() if section_el else ""
                price = self._pick_lowest_price(price_txt)

            if price is None or price <= 0:
                return None
            # Mantık kontrolü: eski fiyat yeni fiyattan düşükse veya eşitse
            # gerçek bir indirim yok demektir, temizle.
            if original_price is not None and original_price <= price:
                original_price = None

            # Resim
            img_el = await card.query_selector("img[data-testid='image-img'], img")
            image_url = None
            if img_el:
                image_url = (
                    await img_el.get_attribute("src")
                    or await img_el.get_attribute("data-src")
                )

            return ProductListing(
                url=href.split("?")[0],  # query param'ları temizle
                name=full_name,
                price=price,
                site=self.site_name,
                brand=brand.lower(),
                image_url=image_url,
                original_price=original_price,
            )
        except Exception as exc:
            log.debug("Trendyol kart parse hatası: %s", exc)
            return None

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

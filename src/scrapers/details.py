"""Ürün sayfasından açıklama metni çekme (kahve profili için ham girdi).

Son doğrulama: 2026-11-09. Arama sonucu kartlarında yalnız ad + fiyat var;
kavrum, aroma notaları, menşei, Arabica oranı gibi bilgiler ürün sayfasında.
Bu modül sayfayı açıp ilgili blokları düz metin olarak döndürür; yorumlamayı
`src.core.classify` (Gemini) yapar.

Kaynaklar:
  trendyol    .product-description-section (açıklama) + .attribute-sections (özellikler)
  hepsiburada #Description (açıklama + "Ürün özellikleri": lezzet, aroma...)
  amazon_tr   "Ürün Detayları" özellik bölümü (kavurma seviyesi vb.) +
              #feature-bullets + #productDescription
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

log = logging.getLogger(__name__)

SELECTORS: dict[str, list[str]] = {
    "trendyol": [".product-description-section", ".product-description-content",
                 "#product-content-wrapper", ".attribute-sections"],
    "hepsiburada": ["#Description"],
    "amazon_tr": [".voyager-ns-desktop-attribute-sections", "#feature-bullets",
                  "#productDescription"],
}
HOMEPAGE = {
    "hepsiburada": "https://www.hepsiburada.com/",
}
MAX_CHARS = 3000

# Kahveyle ilgisi olmayan satıcı/kargo/mevzuat kalıpları — satır bazında atılır
_NOISE = re.compile(
    r"satıcı|kargo|sipariş|iade|stok|kampanya fiyat|gönderilecek|teslimat|güvenlik bilgi|"
    r"hatalı içerik|detayları gör|tümünü gör|stok kodu|garanti|fatura|tıklayın|"
    r"daha fazla göster|barkod|yıldız üzerinden|ithalatçı|muhafaza|alerji|tüketim tarihi|domuz",
    re.IGNORECASE,
)
# Amazon özellik bölümü tek satır; satış sıralaması/yorumlar aynı satırda başlar → oradan kes
_CUT = re.compile(r"En Çok Satanlar Sıralaması|Müşteri Yorumları|Ölçümler Birim", re.IGNORECASE)


def clean(texts: list[str]) -> Optional[str]:
    """Blokları satırlara böl, gürültüyü ve tekrarları at, birleştir."""
    seen: set[str] = set()
    lines: list[str] = []
    for t in texts:
        for line in (t or "").splitlines():
            line = re.sub(r"\s+", " ", _CUT.split(line)[0]).strip()
            if len(line) < 3 or _NOISE.search(line):
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            lines.append(line)
    out = "\n".join(lines).strip()
    return out[:MAX_CHARS] if len(out) >= 20 else None


async def fetch_description(page: "Page", site: str, url: str) -> Optional[str]:
    """Açık bir sayfada ürün URL'sine gidip açıklama metnini döndür."""
    sels = SELECTORS.get(site)
    if not sels:
        return None
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    if resp is not None and resp.status >= 400:
        raise RuntimeError(f"HTTP {resp.status}")
    await page.wait_for_timeout(1500)
    # Açıklama blokları çoğu sitede aşağıda ve tembel yükleniyor
    await page.evaluate("window.scrollBy(0, 2500)")
    await page.wait_for_timeout(1200)
    texts = await page.evaluate(
        """(sels) => sels.flatMap(s => [...document.querySelectorAll(s)].map(e => e.innerText || ''))""",
        sels,
    )
    return clean(texts)


async def fetch_many(
    context: "BrowserContext",
    site: str,
    urls: list[str],
    *,
    delay_ms: int = 2000,
    amazon_scraper=None,
) -> dict[str, tuple[Optional[str], Optional[str]]]:
    """URL -> (açıklama, hata). Tek sayfa açılır, sırayla gezilir.

    Amazon için tarama sırasında ısınmış scraper verilirse onun oturumu
    (aws-waf-token) kullanılır; yoksa önce ana sayfadan ısınılır.
    """
    out: dict[str, tuple[Optional[str], Optional[str]]] = {}
    if not urls:
        return out
    page = await context.new_page()
    try:
        if site == "amazon_tr" and amazon_scraper is not None:
            await amazon_scraper._ensure_session(page)
        elif site in HOMEPAGE:
            try:
                await page.goto(HOMEPAGE[site], wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(1200)
            except Exception:
                pass
        for url in urls:
            try:
                desc = await fetch_description(page, site, url)
                out[url] = (desc, None if desc else "açıklama bulunamadı")
            except Exception as exc:  # tek ürünün hatası diğerlerini durdurmasın
                out[url] = (None, f"{type(exc).__name__}: {exc}"[:200])
            await page.wait_for_timeout(delay_ms)
    finally:
        await page.close()
    return out

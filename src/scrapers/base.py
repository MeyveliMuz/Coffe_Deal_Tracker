"""Scraper temel sınıfı: her site kendi alt sınıfını sağlar."""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from src.core.models import ProductListing

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext


log = logging.getLogger(__name__)


class ScraperError(Exception):
    """Scraping hatası (network, parse, bot koruması vb.)."""


class BotProtectionError(ScraperError):
    """Site bot koruması tetikledi (CAPTCHA, 403, challenge page)."""


class BaseScraper(ABC):
    site_name: str = "base"

    def __init__(
        self,
        context: "BrowserContext",
        *,
        max_products: int = 15,
        request_delay_ms: int = 2000,
        search_suffix: str = "kahve çekirdeği",
    ) -> None:
        self.context = context
        self.max_products = max_products
        self.request_delay_ms = request_delay_ms
        self.search_suffix = search_suffix

    @abstractmethod
    async def search(self, brand: str) -> list[ProductListing]:
        """Verilen marka için sitedeki ürünleri döndür.

        Hata fırlatabilir (ScraperError, BotProtectionError). Bir sayfadaki
        tek bir ürün parse hatası istenmiyor — alt sınıflar sessizce atlasın.
        """

    # Ortak yardımcılar -------------------------------------------------------
    async def _polite_wait(self) -> None:
        await asyncio.sleep(self.request_delay_ms / 1000)

    def _build_query(self, brand: str) -> str:
        suffix = self.search_suffix.strip()
        return f"{brand} {suffix}".strip() if suffix else brand

    @staticmethod
    def _parse_price_tr(text: str) -> float | None:
        """'1.234,56 TL' gibi TR formatlı fiyatı float'a çevir."""
        if not text:
            return None
        import re

        cleaned = re.sub(r"[^0-9.,]", "", text.strip())
        if not cleaned:
            return None
        # TR format: binlik '.', ondalık ','
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        else:
            # Sadece '.' varsa — binlik ayırıcı olabilir (1.234) veya ondalık (1.23)
            # İki haneli ondalık olasılığı yüksek değil; binlik olarak kaldır
            parts = cleaned.split(".")
            if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
                cleaned = cleaned.replace(".", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _brand_matches(product_name: str, brand: str) -> bool:
        """Ürün adında marka geçiyor mu (case-insensitive kelime sınırlı)?"""
        import re

        pattern = r"\b" + re.escape(brand.strip()) + r"\b"
        return bool(re.search(pattern, product_name, re.IGNORECASE))

    # Sadece çekirdek kahve istiyoruz; öğütülmüş/kapsül/granül/filtre/instant
    # ürünleri ürün adına bakıp eliyoruz. Arama suffix'i "kahve çekirdeği"
    # olsa bile sonuçlara karışıyorlar.
    _NON_BEAN_KEYWORDS = (
        "öğütülmüş", "ogutulmus",
        "kapsül", "kapsul",
        "granül", "granul",
        "filtre kahve", "filtre  kahve",
        "instant", "hazır kahve", "hazir kahve",
        "pod", "tablet",
        "nespresso uyumlu", "dolce gusto",
        "türk kahvesi", "turk kahvesi",
    )

    @classmethod
    def _is_whole_bean(cls, product_name: str) -> bool:
        name = product_name.lower()
        # Pozitif kontrol: ad "kahve" veya "coffee" içermeli — kahve markaları
        # giyim/aksesuar gibi alakasız ürünler de satıyor (ör. "Tchibo
        # Dokuma Pijama Takımı"), bunları en başta eleyelim.
        if "kahve" not in name and "coffee" not in name:
            return False
        if any(kw in name for kw in cls._NON_BEAN_KEYWORDS):
            return False
        return True

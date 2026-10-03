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
        product_types: list[str] | None = None,
    ) -> None:
        self.context = context
        self.max_products = max_products
        self.request_delay_ms = request_delay_ms
        self.search_suffix = search_suffix
        # Hangi ürün türleri kabul edilsin. None → varsayılan (yalnızca çekirdek).
        self.allowed_types: set[str] = set(product_types or ["cekirdek"])

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
        # Çekirdek dışı türler de isteniyorsa, çekirdeğe özgü arama sorgusu
        # ("... kahve çekirdeği") sonuçları gereksiz daraltır. Bu durumda
        # genel "kahve" araması yapıp türü sonradan filtreleriz.
        if self.allowed_types and self.allowed_types != {"cekirdek"}:
            suffix = "kahve"
        return f"{brand} {suffix}".strip() if suffix else brand

    @staticmethod
    def _parse_price_tr(text: str) -> float | None:
        """Fiyat metnini float'a çevir — TR ('1.234,56 TL') ve EN ('1,234.56 TL')
        biçimlerinin ikisini de doğru okur.

        Site hangi biçimi sunacağını değiştirebiliyor: Trendyol 2026-10-02
        taramasında EN biçimi döndü ve eski "nokta=binlik, virgül=ondalık"
        varsayımı fiyatları 1000 kat küçülttü (2,279.90 → 2.2799). Kural:
          - İki ayıraç da varsa SONUNCUSU ondalıktır.
          - Tek tür ayıraç varsa: birden çok geçiyorsa ya da son ayıraçtan
            sonra tam 3 hane varsa binliktir (kuruş en fazla 2 hane),
            aksi halde ondalıktır.
        """
        if not text:
            return None
        import re

        cleaned = re.sub(r"[^0-9.,]", "", text.strip()).strip(".,")
        if not cleaned:
            return None
        last_dot, last_comma = cleaned.rfind("."), cleaned.rfind(",")
        if last_dot != -1 and last_comma != -1:
            dec = "." if last_dot > last_comma else ","
            thousands = "," if dec == "." else "."
            cleaned = cleaned.replace(thousands, "").replace(dec, ".")
        elif last_dot != -1 or last_comma != -1:
            sep = "." if last_dot != -1 else ","
            tail = cleaned.rsplit(sep, 1)[1]
            if cleaned.count(sep) > 1 or len(tail) == 3:
                cleaned = cleaned.replace(sep, "")
            else:
                cleaned = cleaned.replace(sep, ".")
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

    # Ürün türü sınıflandırması — ürün adındaki anahtar kelimelere bakar.
    # Sıra önemli: bir kahve çekirdek dışı bir türe ait anahtar kelime
    # içeriyorsa o türe atanır; hiçbiriyle eşleşmezse varsayılan "cekirdek".
    _TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("kapsul", ("kapsül", "kapsul", "pod", "tablet",
                    "nespresso uyumlu", "dolce gusto")),
        ("instant", ("granül", "granul", "instant",
                     "hazır kahve", "hazir kahve")),
        ("ogutulmus", ("öğütülmüş", "ogutulmus")),
        ("filtre", ("filtre kahve", "filtre  kahve")),
        ("turk", ("türk kahvesi", "turk kahvesi")),
    )

    @classmethod
    def _classify_product(cls, product_name: str) -> str | None:
        """Ürünün türünü döndür (cekirdek/ogutulmus/kapsul/filtre/turk/instant).
        Kahve ürünü değilse None."""
        name = product_name.lower()
        # Pozitif kontrol: ad "kahve" veya "coffee" içermeli — kahve markaları
        # giyim/aksesuar gibi alakasız ürünler de satıyor (ör. "Tchibo
        # Dokuma Pijama Takımı"), bunları en başta eleyelim.
        if "kahve" not in name and "coffee" not in name:
            return None
        for type_key, keywords in cls._TYPE_KEYWORDS:
            if any(kw in name for kw in keywords):
                return type_key
        # Özel bir tür belirten kelime yoksa çekirdek varsay
        return "cekirdek"

    def _product_allowed(self, product_name: str) -> bool:
        """Ürün, seçili türlerden birine ait mi?"""
        category = self._classify_product(product_name)
        if category is None:
            return False
        # allowed_types boşsa (kullanıcı hepsini kapattıysa) hiçbir şey gelmez;
        # bu kasıtlı — en az bir tür seçili olması beklenir.
        return category in self.allowed_types

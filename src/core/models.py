from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ProductListing:
    """Bir scraper tarafından bir sitede bulunan ham ürün kaydı."""
    url: str
    name: str
    price: float
    site: str
    brand: str
    image_url: Optional[str] = None
    currency: str = "TRY"
    # Sitede üstü çizili eski fiyat (strikethrough/list price). Kart üzerinde
    # indirim etiketi varsa scraper bunu doldurur — uygulama geçmişi olmasa
    # bile bunu fırsat olarak işaretleyebilir.
    original_price: Optional[float] = None


@dataclass(frozen=True)
class Deal:
    """Son 30 gün en düşüğüne eşit/altında olan ürün."""
    listing: ProductListing
    historical_min: Optional[float]  # mevcut tarama HARİÇ pencere içindeki en düşük; geçmiş yoksa None
    history_points: int    # mevcut tarama hariç kaç önceki kayıt var
    discount_pct: Optional[float] = None  # ilgili indirim yüzdesi (geçmiş veya site bazlı)
    original_price: Optional[float] = None  # site kartındaki üstü çizili eski fiyat (varsa)
    previous_logged_price: Optional[float] = None  # en son önceki tarama fiyatı (kalıcı değişim için)

    @property
    def is_new_low(self) -> bool:
        return self.historical_min is not None and self.listing.price < self.historical_min


@dataclass
class ScanSummary:
    sites_scanned: int = 0
    brands_scanned: int = 0
    products_found: int = 0
    deals_found: int = 0
    errors: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # bot koruması vb. (hata değil)
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None

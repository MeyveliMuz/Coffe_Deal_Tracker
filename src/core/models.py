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


@dataclass(frozen=True)
class Deal:
    """Son 30 gün en düşüğüne eşit/altında olan ürün."""
    listing: ProductListing
    historical_min: float  # mevcut tarama HARİÇ pencere içindeki en düşük
    history_points: int    # mevcut tarama hariç kaç önceki kayıt var
    discount_pct: Optional[float] = None  # (historical_min - current) / historical_min * 100

    @property
    def is_new_low(self) -> bool:
        return self.listing.price < self.historical_min


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

"""config.json yükleyici."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Ürün türü kategorileri (anahtar → ekranda görünen ad). Marka filtresi gibi
# kullanıcı kutucuklarla seçer; scraper bu listeye göre ürünleri eler.
PRODUCT_TYPES: dict[str, str] = {
    "cekirdek": "Çekirdek",
    "ogutulmus": "Öğütülmüş",
    "kapsul": "Kapsül",
    "filtre": "Filtre",
    "turk": "Türk Kahvesi",
    "instant": "Granül / Hazır",
}


@dataclass(frozen=True)
class AppConfig:
    brands: list[str]
    sites: list[str]
    history_days: int = 90
    max_products_per_brand_per_site: int = 15
    request_delay_ms: int = 2000
    headless: bool = True
    search_suffix: str = "kahve çekirdeği"
    # Hangi ürün türleri sonuçlara dahil edilsin (bkz. PRODUCT_TYPES).
    # Varsayılan: yalnızca çekirdek — mevcut davranış.
    product_types: list[str] = field(default_factory=lambda: ["cekirdek"])
    # Windows oturum açılışında uygulamayı otomatik başlat (registry Run anahtarı).
    start_with_windows: bool = False
    # Uygulama her açıldığında otomatik bir tarama başlat.
    auto_scan_on_launch: bool = False

    @classmethod
    def load(cls, path: Path | str) -> "AppConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        raw_types = data.get("product_types", ["cekirdek"])
        product_types = [
            str(t).strip().lower() for t in raw_types if str(t).strip()
        ] or ["cekirdek"]
        return cls(
            brands=[str(b).strip().lower() for b in data.get("brands", [])],
            sites=[str(s).strip().lower() for s in data.get("sites", [])],
            history_days=int(data.get("history_days", 90)),
            max_products_per_brand_per_site=int(data.get("max_products_per_brand_per_site", 15)),
            request_delay_ms=int(data.get("request_delay_ms", 2000)),
            headless=bool(data.get("headless", True)),
            search_suffix=str(data.get("search_suffix", "kahve çekirdeği")),
            product_types=product_types,
            start_with_windows=bool(data.get("start_with_windows", False)),
            auto_scan_on_launch=bool(data.get("auto_scan_on_launch", False)),
        )

    def to_dict(self) -> dict:
        return {
            "brands": list(self.brands),
            "sites": list(self.sites),
            "history_days": self.history_days,
            "max_products_per_brand_per_site": self.max_products_per_brand_per_site,
            "request_delay_ms": self.request_delay_ms,
            "headless": self.headless,
            "search_suffix": self.search_suffix,
            "product_types": list(self.product_types),
            "start_with_windows": self.start_with_windows,
            "auto_scan_on_launch": self.auto_scan_on_launch,
        }

    def save(self, path: Path | str) -> None:
        """Ayarları config.json'a yaz (tek kaynak). Atomik: önce .tmp'ye yaz,
        sonra taşı — yazma yarıda kesilirse config bozulmasın."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)


def _is_frozen() -> bool:
    """PyInstaller ile paketlenmiş mi?"""
    import sys

    return getattr(sys, "frozen", False)


def project_root() -> Path:
    """Geliştirme: src/core/config.py → proje kökü.
    Paketli: exe'nin bulunduğu klasör.
    """
    import sys

    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def _bundle_root() -> Path:
    """PyInstaller ile paketlenmiş sabit kaynakların bulunduğu yer."""
    import sys

    if _is_frozen():
        return Path(getattr(sys, "_MEIPASS", sys.executable))
    return project_root()


def default_config_path() -> Path:
    # Önce exe yanındaki (kullanıcı tarafından düzenlenebilir) config'i kontrol et,
    # yoksa bundle içindekine düş.
    user_cfg = project_root() / "config.json"
    if user_cfg.exists():
        return user_cfg
    return _bundle_root() / "config.json"


def user_config_path() -> Path:
    """Ayarların YAZILACAĞI konum. Her zaman exe/proje kökü altında —
    paketli modda bundle (_MEIPASS) salt-okunur olduğu için oraya yazılmaz."""
    return project_root() / "config.json"


def default_db_path() -> Path:
    """Her zaman yazılabilir konumda: exe/proje kökünde data/ altında."""
    return project_root() / "data" / "price_history.db"

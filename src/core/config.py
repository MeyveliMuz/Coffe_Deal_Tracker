"""config.json yükleyici."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    brands: list[str]
    sites: list[str]
    history_days: int = 30
    max_products_per_brand_per_site: int = 15
    request_delay_ms: int = 2000
    headless: bool = True
    search_suffix: str = "kahve çekirdeği"

    @classmethod
    def load(cls, path: Path | str) -> "AppConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            brands=[str(b).strip().lower() for b in data.get("brands", [])],
            sites=[str(s).strip().lower() for s in data.get("sites", [])],
            history_days=int(data.get("history_days", 30)),
            max_products_per_brand_per_site=int(data.get("max_products_per_brand_per_site", 15)),
            request_delay_ms=int(data.get("request_delay_ms", 2000)),
            headless=bool(data.get("headless", True)),
            search_suffix=str(data.get("search_suffix", "kahve çekirdeği")),
        )


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


def default_db_path() -> Path:
    """Her zaman yazılabilir konumda: exe/proje kökünde data/ altında."""
    return project_root() / "data" / "price_history.db"

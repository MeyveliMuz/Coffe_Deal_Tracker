"""Fiyat ayrıştırma + aykırı fiyat koruması (CI). Tarayıcı gerektirmez.

Gerileme: 2026-10-02'de Trendyol EN sayı biçimi döndürdü ('2,279.90 TL');
eski TR-varsayımlı parser bunu 2.2799 okuyup sahte %99.9 fırsat üretti.
"""
import pytest

from src.core.scan_engine import _is_price_outlier
from src.scrapers.base import BaseScraper
from src.scrapers.trendyol import TrendyolScraper

parse = BaseScraper._parse_price_tr


@pytest.mark.parametrize("text, expected", [
    # TR biçimi
    ("2.279,90 TL", 2279.90),
    ("749,90 TL", 749.90),
    ("1.875 TL", 1875.0),
    ("1.234.567,89", 1234567.89),
    # EN biçimi (Trendyol 2026-10-02)
    ("2,279.90 TL", 2279.90),
    ("1,875 TL", 1875.0),
    ("1,240 TL", 1240.0),
    ("2,676.37 TL", 2676.37),
    ("749.90 TL", 749.90),
    # ayırıcısız / boş
    ("329 TL", 329.0),
    ("", None),
    ("TL", None),
])
def test_parse_price_both_formats(text, expected):
    assert parse(text) == expected


def test_trendyol_unit_price_ignored():
    # Kartın fiyat kutusu artık birim fiyatı da içeriyor
    assert TrendyolScraper._pick_lowest_price("749,90 TL\n(2.999,60 TL/kg)") == 749.90
    assert TrendyolScraper._pick_lowest_price("2,279.90 TL\n(569.98 TL/Adet)") == 2279.90


def test_price_outlier_guard():
    history = [2399.9, 2439.0, 2450.0]
    assert _is_price_outlier(2.3999, history)       # 1000 kat küçük okunmuş
    assert not _is_price_outlier(2099.9, history)   # gerçek indirim
    assert not _is_price_outlier(5.0, [])           # geçmiş yoksa karar verilmez

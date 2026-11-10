"""Ürün türü sınıflandırması — kahve dışı ürünler ve çekirdek olmayan kahveler."""
import pytest

from src.scrapers.base import BaseScraper

C = BaseScraper._classify_product


@pytest.mark.parametrize("name,expected", [
    ("Kahve Dünyası 1000gr Çekirdek Espresso Kahve", "cekirdek"),
    ("The Whirl ESPRESSO STRONG 441°F ÇEKİRDEK KAHVE 1 KG", "cekirdek"),
    ("Lavazza Crema e Aroma Coffee Beans Arabica robusta 1000 g", "cekirdek"),
    ("Kahve Dünyası Lavi Fıstıklı, Sütlü Dolgulu Çikolata 300g", None),
    ("Kahve Dünyası Gofrik Fıstık Parçacıklı Sütlü Mini Gofret 125gr", None),
    ("Kahve Dünyası Çikolata Kaplı Kahve Çekirdeği 100 g", None),
    ("illy Toz Kahve Orta Kavrulmuş 250 Gr", "ogutulmus"),
    ("The Whirl Brunette 431°F Çekilmiş Kahve 250 gr", "ogutulmus"),
    ("Kahve Dünyası 2'si 1 Arada Klasik 40'lı Paket", "instant"),
    ("Kahve Dünyası 3ü1 Arada Fındıklı Kahve 18g 40 Adet", "instant"),
    ("Jacobs Monarch Gold Kahve 600 Gr Eko Paket", "instant"),
    ("Tchibo Dokuma Pijama Takımı", None),
])
def test_classify_product(name, expected):
    assert C(name) == expected

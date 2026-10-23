"""Ürün adından gramaj çıkarma — gerçek ürün adlarından örnekler."""
import pytest

from src.core.weight import parse_weight


@pytest.mark.parametrize("name, total, label", [
    ("Tchibo Barista Espresso Çekirdek Kahve 500 g", 500, "500 g"),
    ("Tchibo Eduscho Caffe Crema Prof. Kahve 1kg", 1000, "1 kg"),
    ("Tchibo Barista Caffé Créme Çekirdek Kahve 1000 Gr.", 1000, "1 kg"),
    ("illy Toz Kahve (2x250gr) Orta Kavrulmuş", 500, "2 × 250 g"),
    ("Lavazza Crema E Aroma 2 x 1 kg Çekirdek Kahve", 2000, "2 × 1 kg"),
    ("The Whirl Filtre Tanned Kahve 250 gr X 2 Adet", 500, "2 × 250 g"),
    ("Tchibo Davidoff Cafe Creme Çekirdek Kahve 500 gr - 2 Adet", 1000, "2 × 500 g"),
    ("Tchibo Gold Selection Çekirdek Kahve 1000 gr 2 Lİ", 2000, "2 × 1 kg"),
    ("Tchibo Professional Espresso Çekirdek Kahve 2 Adet 1kg", 2000, "2 × 1 kg"),
    ("Lavazza Crema E Aroma Çekirdek Kahve, 3lü Paket, 3 x 1000g", 3000, "3 × 1 kg"),
    ("Lavazza Super Crema Çekirdek Kahve 1 Kgx2 Adet", 2000, "2 × 1 kg"),
    # sonraki parantez açıklaması toplamı değiştirmez
    ("Julius Meinl Jubilaum 1 Kg Çekirdek Kahve (2 Adet 500 Gr)", 1000, "1 kg"),
    ("The Whirl Espresso 441°F Çekirdek Kahve 250 G", 250, "250 g"),
])
def test_parse_weight(name, total, label):
    w = parse_weight(name)
    assert w["total_g"] == total and w["label"] == label


@pytest.mark.parametrize("name", [
    "illy Arabica Selection Çekirdek Kahve Tanışma Seti",
    "The Whirl Filtre Brunette 431°f Çekilmiş Kahve 4'lü Tanışma Paketi",
    "Lavazza %100 Arabica Çekirdek Kahve",
])
def test_no_weight(name):
    assert parse_weight(name) is None

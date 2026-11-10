"""Ürün açıklaması temizleme, profil normalize etme, .env okuma, DB ayrıntı tablosu."""
from src.core.classify import load_api_key, normalize
from src.scrapers.details import clean
from src.storage.db import PriceDatabase


def test_clean_drops_seller_noise_and_duplicates():
    texts = [
        "Ürün Açıklaması\nJulius Meinl President orta kavrum, çikolata notaları.\n"
        "Bu ürün e-grossmarket tarafından gönderilecektir.\n"
        "Bir ürün, birden fazla satıcı tarafından satılabilir.",
        "Julius Meinl President orta kavrum, çikolata notaları.\nMenşei AT",
    ]
    out = clean(texts)
    assert "çikolata" in out and "Menşei AT" in out
    assert "satıcı" not in out and "gönderilecektir" not in out
    assert out.count("Julius Meinl President") == 1
    assert clean(["Kargo bedava", ""]) is None


def test_normalize_clamps_model_output():
    p = normalize({
        "roast": "orta", "bean": "uzaylı", "arabica_pct": 140, "origin": ["Brezilya", " "],
        "flavor_notes": ["Çikolata", "Karamel"], "acidity": "düşük", "body": "dolgun",
        "intensity": 8.6, "brew_methods": ["espresso", "çaydanlık"], "decaf": 0,
        "source": "açıklama", "summary": "x",
    })
    assert p["bean"] == "bilinmiyor" and p["arabica_pct"] is None
    assert p["origin"] == ["Brezilya"] and p["flavor_notes"] == ["çikolata", "karamel"]
    assert p["intensity"] == 5 and p["brew_methods"] == ["espresso"] and p["decaf"] is False


def test_load_api_key_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert load_api_key(tmp_path) is None
    (tmp_path / ".env").write_text('# yorum\nGEMINI_API_KEY="abc123"\n', encoding="utf-8")
    assert load_api_key(tmp_path) == "abc123"


def test_details_table_roundtrip(tmp_path):
    db = PriceDatabase(tmp_path / "t.db")
    try:
        urls = ["u1", "u2", "u3"]
        assert db.urls_needing_details(urls, 2) == ["u1", "u2"]
        db.save_details("u1", "orta kavrum", None)
        db.save_details("u2", None, "HTTP 404")  # hata: 7 gün tekrar denenmez
        assert db.urls_needing_details(urls, 5) == ["u3"]
        assert db.details_stats()["described"] == 1
    finally:
        db.close()


def test_clean_cuts_amazon_ranking_but_keeps_attributes():
    line = ("Ürün Detayları Marka Adı Tchibo Kahve Kavurma Seviyesi Orta Kavrulmuş "
            "En Çok Satanlar Sıralaması Gıda Ürünleri Şu kategoride 352. sırada")
    out = clean([line, "Barkod No: 4046234873535\nYoğunluk: 6 üzerinden 3"])
    assert "Orta Kavrulmuş" in out and "352" not in out
    assert "Barkod" not in out and "Yoğunluk: 6 üzerinden 3" in out


def test_load_api_key_bare_value(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")
    assert load_api_key(tmp_path) == "abcdefghijklmnopqrstuvwxyz123456"
    (tmp_path / ".env").write_text("FOO=bar\n", encoding="utf-8")
    assert load_api_key(tmp_path) is None


def test_roast_from_name_temperature():
    from src.core.classify import roast_from_name
    assert roast_from_name("The Whirl Filtre Tanned 423°F Çekilmiş Kahve") == "orta"
    assert roast_from_name("The Whirl Espresso Brunette 441°f Çekirdek Kahve") == "orta-koyu"
    assert roast_from_name("Tchibo Barista Espresso 1 kg") is None
    assert roast_from_name("%100 Arabica 99°F") is None  # anlamsız değer

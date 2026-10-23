"""Referans fiyat doğrulaması (sahte indirim elemesi) — saf karar fonksiyonu."""
from src.core.deal_detector import assess, count_spikes

# The Whirl 1 kg (Hepsiburada, Eki 2026): aylarca ~1.440 TL, arada 1 günlük
# sıçramalar; sayfa 2.399,90'ın üstünü çizip "%40 indirim" diyor.
FLAT = [1439.94] * 12
WHIRL_60 = [1309.9] * 10 + [2203.9] + [1309.9] * 12 + [1439.94] * 4 + [2049.9] + FLAT
WHIRL_30 = [1439.94] * 4 + [2049.9] + FLAT


def test_fake_badge_with_spikes():
    a = assess(1439.94, 2399.9, WHIRL_30, WHIRL_60, window_min=1309.9)
    assert a["verdict"] == "fake"
    assert a["discount_pct"] == 0.0 and round(a["claimed_pct"]) == 40
    assert a["badge_seen"] == f"0/{len(WHIRL_60)}"
    assert a["spikes"] == 2
    assert "gerçek indirim yok" in a["reason"]


def test_price_went_up_but_badge_says_discount():
    a = assess(699.0, 789.0, [590.75] * 10, [590.75] * 20)
    assert a["verdict"] == "fake" and "yüksek" in a["reason"]


def test_genuine_discount_uses_30d_low_not_badge():
    # 30 gün boyunca 1.349,90; şimdi 1.008,59 → gerçek indirim %25,3
    a = assess(1008.59, 1215.04, [1349.9] * 20, [1349.9] * 40)
    assert a["verdict"] == "verified"
    assert round(a["discount_pct"], 1) == 25.3


def test_inflated_claim_reports_real_pct():
    # gerçekten düşmüş (%5) ama sayfa %40 diyor
    a = assess(950.0, 1583.0, [1000.0] * 20, [1000.0] * 40)
    assert a["verdict"] == "verified" and round(a["discount_pct"]) == 5
    assert "abartılı" in a["reason"]


def test_new_product_is_unverified():
    a = assess(500.0, 700.0, [], [])
    assert a["verdict"] == "unverified" and round(a["discount_pct"]) == 29


def test_no_badge_no_drop_is_not_a_deal():
    assert assess(1000.0, None, [1000.0] * 20, [1000.0] * 40) is None


def test_spike_counting():
    assert count_spikes([100] * 5 + [150] + [100] * 5 + [150, 150] + [100] * 5) == 2
    assert count_spikes([100] * 5 + [150] * 5 + [100] * 5) == 0   # uzun süreli artış sıçrama değil
    assert count_spikes([100] * 10 + [150]) == 0                   # sondaki yükseliş sayılmaz

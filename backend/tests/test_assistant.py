"""Asistan araçları, bütçe ve tercih hafızası — Gemini çağırmadan."""
from src.core.config import AppConfig

from backend import assistant, budget, preferences


def test_cost_and_model_switch():
    assert budget.cost_usd("gemini-3.1-flash-lite", 1_000_000, 0) == 0.25
    assert budget.cost_usd("bilinmeyen-model", 1_000_000, 0) == 2.0  # temkinli: Pro fiyatı
    assert budget.chat_model({"spent_try": 10, "budget_try": 70})[1] == "akıllı"
    assert budget.chat_model({"spent_try": 40, "budget_try": 70}) == (budget.CHAT_ECONOMY, "tasarruf")


def _item(i, brand, ppk, roast=None, notes=(), g=1000, verdict=None):
    return {"id": f"id{i}", "url": f"u{i}", "name": f"{brand} kahve {i}", "brand": brand, "site": "trendyol",
            "weight": "1 kg", "weight_g": g, "price_tl": ppk * g / 1000, "price_per_kg": ppk, "market": "orta",
            "discount": {"verdict": verdict, "pct": 10.0, "page_claim_pct": 10.0} if verdict else None,
            "profile": {"roast": roast, "flavor_notes": list(notes), "brew_methods": ["moka"]} if roast else None}


CAT = [_item(1, "lavazza", 1700, "orta", ["çikolata"]), _item(2, "tchibo", 1200, "koyu", ["fındık"], verdict="sahte"),
       _item(3, "tchibo", 1300), _item(4, "illy", 2500, "orta", ["karamel"], g=250, verdict="gerçek")]


def test_search_filters_and_sort():
    r = assistant._search(CAT, {"brand": "tchibo"})
    assert [p["id"] for p in r["products"]] == ["id2", "id3"]  # kilo fiyatına göre artan
    assert assistant._search(CAT, {"flavor": "çikolata"})["total_matches"] == 1
    assert assistant._search(CAT, {"max_price_per_kg": 1250})["products"][0]["id"] == "id2"
    assert [p["id"] for p in assistant._search(CAT, {"real_deals_only": True})["products"]] == ["id4"]
    assert assistant._search(CAT, {"size": "250"})["total_matches"] == 1


def test_search_hint_when_profile_filters_find_nothing():
    r = assistant._search(CAT, {"flavor": "çiçeksi"})
    assert r["total_matches"] == 0 and "KALDIRIP" in r["hint"]


def test_update_settings_validates_and_saves(monkeypatch):
    cfg = AppConfig(brands=["lavazza", "tchibo"], sites=["trendyol"], schedule_enabled=True, schedule_time="10:00")
    saved = {}
    monkeypatch.setattr(assistant.services, "load_config", lambda: saved.get("cfg", cfg))
    monkeypatch.setattr(assistant.services, "save_config", lambda c: saved.update(cfg=c))
    monkeypatch.setattr(assistant.scheduler, "reschedule", lambda c: None)

    r = assistant._update_settings({"add_brands": ["Segafredo"], "remove_brands": ["tchibo"],
                                    "sites": ["trendyol", "uydurma_site"], "auto_scan_time": "9:30"})
    assert r["ok"] and saved["cfg"].brands == ["lavazza", "segafredo"]
    assert saved["cfg"].sites == ["trendyol"] and saved["cfg"].schedule_time == "09:30"
    assert assistant._update_settings({"remove_brands": ["lavazza", "segafredo"]})["ok"] is False  # boş kalamaz


def test_preferences_remember_forget(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_path", lambda: tmp_path / "p.json")
    preferences.remember("like", "Lavazza Qualità Oro (moka pot)")
    preferences.remember("dislike", "Tchibo koyu kavrumlar")
    preferences.remember("like", "lavazza qualità oro (moka pot)")  # tekrar → tek kayıt
    assert len(preferences.load()) == 2
    assert "SEVMEZ: Tchibo koyu kavrumlar" in preferences.as_text()
    n, left = preferences.forget("tchibo")
    assert n == 1 and len(left) == 1


def test_wallet_spreads_balance_until_end_date(tmp_path, monkeypatch):
    from datetime import datetime
    spent = {"usd": 0.0}
    monkeypatch.setattr(budget, "_wallet_path", lambda: tmp_path / "w.json")
    monkeypatch.setattr(budget, "_tracked_try", lambda since, usd_try: (
        {"chat": {"calls": 1, "input_tokens": 0, "output_tokens": 0, "cost_try": spent["usd"] * usd_try}}
        if spent["usd"] else {}))
    t0 = datetime(2026, 11, 10)
    budget.set_balance(300.0, "2027-01-31", now=t0)
    s = budget.status(now=t0)
    # 10 Kas – 31 Oca = 83 gün; Kasım'a düşen 21 gün
    assert abs(s["budget_try"] - 300 * 21 / 83) < 0.01 and s["chat_mode"] == "akıllı"
    spent["usd"] = 1.0  # 50 TL takip edilen → ×1.3 = 65 TL tahmini
    s = budget.status(now=t0)
    assert s["spent_try"] == 65.0 and s["balance_est_try"] == 235.0 and budget.chat_model(s)[1] == "tasarruf"
    # 4 gün sonra kullanıcı gerçek bakiyeyi girer: 300 → 210 (90 TL düştü, 50 TL takip edildi)
    w = budget.set_balance(210.0, now=datetime(2026, 11, 14))
    assert w["calibrated"] and w["until"] == "2027-01-31"
    assert w["cost_factor"] == round(0.5 * 1.3 + 0.5 * 90 / 50, 3)

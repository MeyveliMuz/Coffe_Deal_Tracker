"""Kahve tavsiye asistanı (Gemini, araç çağırma / function calling).

Asistan bütün kataloğu tek seferde almaz; ihtiyaç duydukça ARAÇ çağırır:
ürün arama (filtrelerle), marka özeti, piyasa normu, ayarları okuma/değiştirme,
tarama başlatma/izleme, kullanıcı tercihlerini hatırlama ve önerileri kart
olarak gösterme. Bu hem asistana uygulamayı yönetme yetkisi verir hem de
mesaj başına token'ı (aylık ~70 TL bütçe) düşük tutar.

Uydurma koruması: öneriler yalnız `show_recommendations` ile, katalogdaki
ürün id'leriyle yapılır; bilinmeyen id atılır. Fiyat/indirim/profil verisi
yalnız araç sonuçlarından gelir.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import statistics
from collections import Counter
from datetime import datetime
from typing import Callable, Optional

from src.core.classify import GeminiClient, load_api_key
from src.core.config import PRODUCT_TYPES, AppConfig

from . import budget, enrich, market, preferences, scheduler, services
from .scan_manager import manager
from .schemas import deal_to_dict, product_to_dict

log = logging.getLogger(__name__)

MAX_TURNS = 16      # modele gönderilen son mesaj sayısı
MAX_ROUNDS = 6      # bir kullanıcı mesajında en fazla araç turu
KNOWN_SITES = ("trendyol", "hepsiburada", "amazon_tr")
ROASTS = ("açık", "orta", "orta-koyu", "koyu")
BREWS = ("espresso", "moka", "filtre", "french_press", "turk", "otomatik_makine")

SYSTEM = """Sen "Kahve Asistanı"sın: Coffee Deal Tracker uygulamasının içindeki, Türkiye'de
çekirdek kahve alacak birine yardım eden samimi ve kısa konuşan bir kahve uzmanısın.
Türkçe konuş, "sen" diye hitap et. Kullanıcı kahveden çok anlamıyor olabilir:
terimleri sade anlat, onu yönlendir.

Yapabildiklerin (ARAÇLAR):
- search_products: güncel katalogda ürün ara (marka, ad, kavrum, tat notası, demleme,
  gramaj, kilo fiyatı, yalnız gerçek indirim, sıralama). Her ürünün fiyatı, kilo fiyatı,
  piyasaya göre konumu (ucuz/orta/pahalı), indirim kararı ve varsa kahve profili gelir.
- list_brands: takip edilen markaların özeti (fiyat düzeyi, tipik kavrum/notalar).
- market_overview: dönemin normu (kilo fiyatı ucuz/orta/pahalı eşikleri, son aylar).
- get_settings / update_settings: hangi markalar, siteler, ürün türleri taranıyor;
  marka ekle/çıkar, tür ve site değiştir, otomatik tarama saatini ayarla.
- start_scan / scan_status: hemen tarama başlat (3–6 dk sürer) ve durumunu izle.
- remember_preference / forget_preference: kullanıcının sevdiği/sevmediği kahveleri
  ve alışkanlıklarını kalıcı olarak hatırla.
- show_recommendations: önerdiğin ürünleri kullanıcıya KART olarak göster.
- set_ai_balance: kullanıcı Google AI Studio'daki güncel bakiyesini söylerse (ör. "bakiyem
  640 TL") kaydet; harcama planı buna göre yeniden hesaplanır. get_settings bu ayın yapay
  zekâ payını ve tahmini kalan bakiyeyi de gösterir.

Nasıl çalışırsın:
1. Öneriden önce eksikse öğren (mesaj başına en fazla 1–2 soru): nasıl demliyor
   (espresso makinesi, moka pot, filtre/V60, french press, Türk kahvesi, tam otomatik),
   sevdiği tatlar (çikolata/fındık gibi yumuşak, meyvemsi-asidik, yoğun-sert), sütlü mü sade
   mi, bütçe (kilo fiyatı), gramaj. "Fark etmez" ya da direkt öneri isterse beklemeden öner.
   Kayıtlı tercihleri (aşağıda) zaten biliyorsun; tekrar sorma.
2. Öneri için search_products ile ara (en fazla 2–3 arama; profil filtreleri az sonuç verirse
   filtreyi kaldırıp marka/fiyatla ara), sonra 2–3 ürünü show_recommendations ile göster.
   Öneri yapıyorsan show_recommendations ÇAĞIRMADAN bitirme.
   Metinde her öneri için 1–2 kısa satırda NEDEN uygun olduğunu yaz; fiyatları kart
   gösterdiği için metinde sıralama. Aynı kahvenin birden çok ilanı varsa en ucuzunu seç.
3. Kullanıcı bir kahveyi/markayı sevdiğini ya da sevmediğini, ya da kalıcı bir alışkanlığını
   (demleme yöntemi, sütlü içmesi, bütçesi) söylerse HER BİRİ için remember_preference ÇAĞIR.
   Aracı çağırmadan "not aldım/kaydettim" DEME — bu yalan olur.
4. Katalogda uygun ürün yoksa (ör. takip edilmeyen bir marka ya da öğütülmüş kahve
   istiyorsa): ayarları değiştirmeyi ve tarama başlatmayı ÖNER. Kullanıcı onaylarsa
   update_settings + start_scan çağır. Kullanıcı açıkça "ekle/tara" dediyse onay bekleme.
   Taramayı gereksiz başlatma (sitelere yük ve bot koruması riski): yalnız ayar değişince,
   veri eskiyse (son tarama > 1 gün) ya da kullanıcı isterse.
5. "Bu dönem 1 kg kahve kaç lira", "hangi marka iyi" gibi sorulara market_overview /
   list_brands verisiyle cevap ver; markaları yalnızca fiyat değil profil (kavrum, notalar)
   üzerinden de karşılaştır.

Kurallar:
- Fiyat, indirim ve ürün profilini YALNIZCA araç sonuçlarından al; asla uydurma.
- Profili olmayan ya da "bilinmiyor" alanlarda genel kahve bilgini kullanabilirsin ama
  bunu açıkça söyle ("ürün sayfasında yazmıyor ama genelde ...").
- Sahte indirimli ürünü "indirimde" diye övme; gerekirse uyar.
- Kısa yaz (en fazla ~8 satır), paragraf yerine satır sonları kullan.
"""


# --- katalog -------------------------------------------------------------------
def _pid(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:8]


def _catalog() -> list[dict]:
    cfg = services.load_config()
    products, deals = services.snapshot(cfg)
    deal_of = {d.listing.url: deal_to_dict(d) for d in deals}
    th = market.current_thresholds()
    profiles = enrich.profiles()
    out = []
    for p in products:
        d = product_to_dict(p)
        deal = deal_of.get(p.url)
        prof = profiles.get(p.url)
        out.append({
            "id": _pid(p.url), "url": p.url, "name": d["name"], "brand": d["brand"], "site": d["site"],
            "weight": d["weight_label"], "weight_g": d["weight_g"], "price_tl": round(d["price"], 2),
            "price_per_kg": d["price_per_kg"], "market": market.tier(d["price_per_kg"], d["weight_g"], th),
            "discount": None if deal is None else {
                "verdict": {"verified": "gerçek", "unverified": "doğrulanamadı", "fake": "sahte"}[deal["verdict"]],
                "pct": round(deal["discount_pct"] or 0, 1),
                "page_claim_pct": round(deal["claimed_pct"], 1) if deal["claimed_pct"] else None,
            },
            "profile": prof,
        })
    return out


def _compact(it: dict) -> dict:
    """Modele giden ürün özeti — token tasarrufu için kısa ve boş alansız."""
    out = {k: it[k] for k in ("id", "name", "site", "weight", "price_tl", "price_per_kg", "market") if it.get(k) is not None}
    if it["discount"]:
        out["discount"] = it["discount"]
    p = it["profile"]
    if p:
        prof = {k: p.get(k) for k in ("roast", "bean", "arabica_pct", "origin", "flavor_notes", "acidity",
                                       "body", "intensity", "brew_methods", "decaf", "source")}
        out["profile"] = {k: v for k, v in prof.items() if v not in (None, "bilinmiyor", [], False)}
    else:
        out["profile"] = None
    return out


# --- araçlar --------------------------------------------------------------------
_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def _fold(t: str) -> str:
    """Türkçe harf/büyük-küçük farkını yok say: 'KAHVE DUNYASI' == 'Kahve Dünyası'."""
    return str(t).replace("İ", "i").replace("I", "ı").lower().translate(_FOLD)


def _search(cat: list[dict], a: dict) -> dict:
    res = cat
    if a.get("brand"):
        b = _fold(a["brand"])
        res = [x for x in res if b in _fold(x["brand"]) or b in _fold(x["name"])]
    if a.get("query"):
        words = _fold(a["query"]).split()
        res = [x for x in res if all(w in _fold(x["brand"] + " " + x["name"]) for w in words)]
    if a.get("size"):
        res = [x for x in res if market.size_of(x["weight_g"]) == str(a["size"])]
    if a.get("max_price_per_kg"):
        res = [x for x in res if x["price_per_kg"] and x["price_per_kg"] <= float(a["max_price_per_kg"])]
    if a.get("min_price_per_kg"):
        res = [x for x in res if x["price_per_kg"] and x["price_per_kg"] >= float(a["min_price_per_kg"])]
    if a.get("roast"):
        res = [x for x in res if x["profile"] and x["profile"].get("roast") == a["roast"]]
    if a.get("flavor"):
        f = _fold(a["flavor"])
        res = [x for x in res if x["profile"] and any(f in _fold(n) for n in x["profile"].get("flavor_notes", []))]
    if a.get("brew_method"):
        res = [x for x in res if x["profile"] and a["brew_method"] in x["profile"].get("brew_methods", [])]
    if a.get("real_deals_only"):
        res = [x for x in res if x["discount"] and x["discount"]["verdict"] == "gerçek"]
    sort = a.get("sort") or "price_per_kg"
    if sort == "discount":
        res = sorted(res, key=lambda x: -(x["discount"]["pct"] if x["discount"] else 0))
    elif sort == "price":
        res = sorted(res, key=lambda x: x["price_tl"])
    else:
        res = sorted(res, key=lambda x: x["price_per_kg"] or 1e9)
    limit = max(1, min(20, int(a.get("limit") or 10)))
    out = {"total_matches": len(res), "products": [_compact(x) for x in res[:limit]],
           "note": "profile=null: ürün sayfası açıklaması henüz işlenmedi"}
    if not res and any(a.get(k) for k in ("roast", "flavor", "brew_method")):
        n_prof = sum(1 for x in cat if x["profile"])
        out["hint"] = (f"Profil filtresiyle eşleşme yok. Katalogdaki {len(cat)} ürünün yalnız {n_prof} tanesinin "
                       "profili çıkarıldı; roast/flavor/brew_method filtrelerini KALDIRIP marka, fiyat ve gramajla "
                       "ara, profili olmayanlar için genel bilgini kullan.")
    elif not res:
        out["hint"] = ("Bu ürün/marka şu an katalogda YOK (son taramada bulunmadı). Aynı şeyi farklı yazımla "
                       "TEKRAR ARAMA. Kullanıcıya katalogda olmadığını söyle; benzer ürünler için daha geniş ara "
                       "(yalnız marka ya da yalnız tat/kavrum) veya genel bilginle cevap ver.")
    return out


def _brands(cat: list[dict]) -> dict:
    cfg = services.load_config()
    groups: dict[str, list[dict]] = {}
    for x in cat:
        groups.setdefault(x["brand"], []).append(x)
    out = []
    for b, xs in sorted(groups.items()):
        ppk = [x["price_per_kg"] for x in xs if x["price_per_kg"] and market.size_of(x["weight_g"]) in ("1000", "2000")]
        profs = [x["profile"] for x in xs if x["profile"]]
        roasts = Counter(p["roast"] for p in profs if p.get("roast") not in (None, "bilinmiyor"))
        notes = Counter(n for p in profs for n in p.get("flavor_notes", []))
        beans = Counter(p["bean"] for p in profs if p.get("bean") not in (None, "bilinmiyor"))
        out.append({"brand": b, "tracked": b in cfg.brands, "products": len(xs),
                    "median_price_per_kg_1kg_plus": round(statistics.median(ppk)) if ppk else None,
                    "profiled": len(profs), "roasts": dict(roasts.most_common(3)),
                    "beans": dict(beans.most_common(2)), "top_notes": [n for n, _ in notes.most_common(5)]})
    untracked = [b for b in cfg.brands if b not in groups]
    return {"brands": out, "tracked_but_no_products": untracked}


def _market() -> dict:
    th = market.current_thresholds()
    labels = {k: v[0] for k, v in market.SIZES.items()}
    o = market.overview("1000")
    return {"last_30_days_tl_per_kg": {labels[k]: {"ucuz_dilim_ust": q[0], "orta": q[1], "pahali_dilim_alt": q[2]}
                                       for k, q in th.items()},
            "1kg_monthly": o["months"][-4:]}


def _settings() -> dict:
    c = services.load_config()
    return {"brands": c.brands, "sites": c.sites, "product_types": c.product_types,
            "available_sites": list(KNOWN_SITES), "available_product_types": PRODUCT_TYPES,
            "auto_scan": {"enabled": c.schedule_enabled, "time": c.schedule_time},
            "max_products_per_brand_per_site": c.max_products_per_brand_per_site,
            "ai_budget": _budget_brief()}


def _budget_brief() -> dict:
    b = budget.status()
    keys = ("spent_try", "budget_try", "remaining_try", "balance_est_try", "until", "chat_mode")
    return {k: b[k] for k in keys if k in b}


def _set_balance(a: dict) -> dict:
    try:
        w = budget.set_balance(float(a.get("balance_try")), a.get("until") or None)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    log.info("Asistan AI bakiyesini güncelledi: %.2f TL", w["balance_try"])
    return {"ok": True, "calibrated": w["calibrated"], "budget": _budget_brief()}


def _update_settings(a: dict) -> dict:
    c = services.load_config()
    brands = list(c.brands)
    changes = []
    for b in a.get("add_brands") or []:
        b = " ".join(str(b).lower().split())
        if b and b not in brands and len(brands) < 20:
            brands.append(b); changes.append(f"+marka {b}")
    for b in a.get("remove_brands") or []:
        b = " ".join(str(b).lower().split())
        if b in brands:
            brands.remove(b); changes.append(f"-marka {b}")
    types = c.product_types
    if a.get("product_types"):
        t = [x for x in a["product_types"] if x in PRODUCT_TYPES]
        if t and t != types:
            types = t; changes.append(f"türler {','.join(t)}")
    sites = c.sites
    if a.get("sites"):
        s = [x for x in a["sites"] if x in KNOWN_SITES]
        if s and s != sites:
            sites = s; changes.append(f"siteler {','.join(s)}")
    sched_on = a["auto_scan_enabled"] if isinstance(a.get("auto_scan_enabled"), bool) else c.schedule_enabled
    sched_time = c.schedule_time
    if a.get("auto_scan_time"):
        hh, _, mm = str(a["auto_scan_time"]).partition(":")
        if hh.isdigit() and mm.isdigit() and 0 <= int(hh) < 24 and 0 <= int(mm) < 60:
            sched_time = f"{int(hh):02d}:{int(mm):02d}"
    if (sched_on, sched_time) != (c.schedule_enabled, c.schedule_time):
        changes.append(f"otomatik tarama {'açık' if sched_on else 'kapalı'} {sched_time}")
    if not brands:
        return {"ok": False, "error": "en az bir marka kalmalı"}
    if not changes:
        return {"ok": True, "changed": [], "settings": _settings()}
    new = AppConfig(**{**c.to_dict(), "brands": brands, "product_types": types, "sites": sites,
                       "schedule_enabled": sched_on, "schedule_time": sched_time})
    services.save_config(new)
    scheduler.reschedule(new)
    log.info("Asistan ayarları değiştirdi: %s", "; ".join(changes))
    return {"ok": True, "changed": changes, "settings": _settings(),
            "note": "Yeni ayarlar bir sonraki taramada geçerli; hemen görmek için start_scan."}


def _scan_status() -> dict:
    s = manager.status_dict()
    from .scheduler import _last_scan_time
    last = _last_scan_time()
    return {"running": s["running"], "progress": s["last_progress"], "products_found": s["products_found"],
            "deals_found": s["deals_found"], "last_scan_finished": last.strftime("%Y-%m-%d %H:%M") if last else None}


_S, _A = "STRING", "ARRAY"
TOOLS = [{"functionDeclarations": [
    {"name": "search_products", "description": "Güncel katalogda çekirdek kahve ara. Filtrelerin hepsi isteğe bağlı.",
     "parameters": {"type": "OBJECT", "properties": {
         "brand": {"type": _S, "description": "marka (ör. lavazza, tchibo)"},
         "query": {"type": _S, "description": "ürün adında geçen kelimeler (ör. 'qualita oro')"},
         "size": {"type": _S, "enum": list(market.SIZES), "description": "paket boyu kovası (gram)"},
         "max_price_per_kg": {"type": "NUMBER"}, "min_price_per_kg": {"type": "NUMBER"},
         "roast": {"type": _S, "enum": list(ROASTS)},
         "flavor": {"type": _S, "description": "tat notası (ör. çikolata, fındık, meyvemsi)"},
         "brew_method": {"type": _S, "enum": list(BREWS)},
         "real_deals_only": {"type": "BOOLEAN", "description": "yalnız doğrulanmış gerçek indirimler"},
         "sort": {"type": _S, "enum": ["price_per_kg", "price", "discount"]},
         "limit": {"type": "INTEGER", "description": "en fazla 20, varsayılan 10"}}}},
    {"name": "list_brands", "description": "Katalogdaki markaların fiyat düzeyi ve tipik profili.",
     "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "market_overview", "description": "Dönemin normu: kilo fiyatı eşikleri ve son aylar.",
     "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "get_settings", "description": "Taranan markalar, siteler, ürün türleri ve otomatik tarama ayarı.",
     "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "update_settings", "description": "Tarama ayarlarını değiştir. Yalnız verilen alanlar değişir.",
     "parameters": {"type": "OBJECT", "properties": {
         "add_brands": {"type": _A, "items": {"type": _S}},
         "remove_brands": {"type": _A, "items": {"type": _S}},
         "product_types": {"type": _A, "items": {"type": _S, "enum": list(PRODUCT_TYPES)}},
         "sites": {"type": _A, "items": {"type": _S, "enum": list(KNOWN_SITES)}},
         "auto_scan_enabled": {"type": "BOOLEAN"},
         "auto_scan_time": {"type": _S, "description": "HH:MM"}}}},
    {"name": "start_scan", "description": "Tüm siteleri hemen tara (3–6 dk). Sonuçlar bitince gelir.",
     "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "scan_status", "description": "Taramanın durumu ve son taramanın zamanı.",
     "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "remember_preference", "description": "Kullanıcının kahve tercihini kalıcı olarak kaydet.",
     "parameters": {"type": "OBJECT", "properties": {
         "kind": {"type": _S, "enum": ["like", "dislike", "note"]},
         "text": {"type": _S, "description": "kısa, ör. 'Lavazza Qualità Oro'yu sever (moka pot)'"}},
         "required": ["kind", "text"]}},
    {"name": "forget_preference", "description": "Metni içeren kayıtlı tercihleri sil.",
     "parameters": {"type": "OBJECT", "properties": {"text": {"type": _S}}, "required": ["text"]}},
    {"name": "set_ai_balance", "description": "Kullanıcının Google AI Studio'daki güncel bakiyesini (TL) kaydet.",
     "parameters": {"type": "OBJECT", "properties": {
         "balance_try": {"type": "NUMBER"},
         "until": {"type": _S, "description": "paranın yetmesi gereken son gün YYYY-MM-DD (yalnız kullanıcı değiştirmek isterse)"}},
         "required": ["balance_try"]}},
    {"name": "show_recommendations", "description": "Önerdiğin ürünleri kullanıcıya kart olarak göster (2–4 ürün).",
     "parameters": {"type": "OBJECT", "properties": {
         "items": {"type": _A, "items": {"type": "OBJECT", "properties": {
             "product_id": {"type": _S}, "reason": {"type": _S, "description": "tek cümle neden"}},
             "required": ["product_id", "reason"]}}},
         "required": ["items"]}},
]}]


class _Session:
    """Tek kullanıcı mesajı boyunca araç durumunu tutar."""

    def __init__(self, start_scan: Callable[[], bool]) -> None:
        self.cat: Optional[list[dict]] = None
        self.start_scan = start_scan
        self.recs: list[dict] = []
        self.actions: list[dict] = []
        self.searches = 0

    def catalog(self) -> list[dict]:
        if self.cat is None:
            self.cat = _catalog()
        return self.cat

    def run(self, name: str, a: dict) -> dict:
        if name == "search_products":
            self.searches += 1
            r = _search(self.catalog(), a)
            if self.searches >= 3:
                r["stop"] = ("Yeterince aradın. Artık ARAMA YAPMA: bulduklarınla cevap ver "
                             "(uygunsa show_recommendations ile kart göster).")
            return r
        if name == "list_brands":
            return _brands(self.catalog())
        if name == "market_overview":
            return _market()
        if name == "get_settings":
            return _settings()
        if name == "update_settings":
            r = _update_settings(a)
            if r.get("changed"):
                self.actions.append({"type": "settings_updated", "changes": r["changed"]})
                self.cat = None
            return r
        if name == "start_scan":
            if manager.running:
                return {"started": False, "reason": "zaten bir tarama sürüyor", **_scan_status()}
            ok = self.start_scan()
            if ok:
                self.actions.append({"type": "scan_started"})
            return {"started": ok, "note": "3–6 dk sürer; bitince kullanıcı tekrar sorabilir"}
        if name == "scan_status":
            return _scan_status()
        if name == "remember_preference":
            items = preferences.remember(a.get("kind", "note"), a.get("text", ""))
            self.actions.append({"type": "preference_saved", "text": a.get("text", "")})
            return {"ok": True, "saved": len(items)}
        if name == "set_ai_balance":
            r = _set_balance(a)
            if r["ok"]:
                self.actions.append({"type": "balance_updated", "text": f"{float(a['balance_try']):.2f} TL"})
            return r
        if name == "forget_preference":
            n, _ = preferences.forget(a.get("text", ""))
            if n:
                self.actions.append({"type": "preference_removed", "text": a.get("text", "")})
            return {"ok": True, "removed": n}
        if name == "show_recommendations":
            by_id = {x["id"]: x for x in self.catalog()}
            shown = 0
            for r in (a.get("items") or [])[:4]:
                x = by_id.get(str(r.get("product_id")))
                if x and all(x["url"] != y["url"] for y in self.recs):
                    self.recs.append({**{k: x[k] for k in ("url", "name", "brand", "site", "weight", "price_tl",
                                                             "price_per_kg", "market", "discount")},
                                      "reason": str(r.get("reason", ""))[:300]})
                    shown += 1
            return {"shown": shown, "note": "kartlar gösterildi" if shown else "geçersiz product_id"}
        return {"error": f"bilinmeyen araç {name}"}


def chat(messages: list[dict], start_scan: Callable[[], bool]) -> dict:
    """messages: [{role: user|assistant, text}] → {reply, recommendations, actions, budget}."""
    key = load_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY yok (.env)")
    if not budget.allowed("chat"):
        b = budget.status()
        return {"reply": f"Bu ayın yapay zekâ payı doldu ({b['spent_try']:.2f} / {b['budget_try']:.2f} TL). "
                         "Bakiyen bitiş tarihine yetsin diye ay başına kadar duruyorum. AI Studio'daki "
                         "bakiyen tahminden yüksekse panelin üstündeki 💳 ile güncelle; pay yeniden hesaplanır.",
                "recommendations": [], "actions": [], "budget": b}

    contents = [
        {"role": "model" if m.get("role") == "assistant" else "user",
         "parts": [{"text": str(m.get("text", ""))[:4000]}]}
        for m in messages[-MAX_TURNS:] if str(m.get("text", "")).strip()
    ]
    if not contents or contents[-1]["role"] != "user":
        raise ValueError("Son mesaj kullanıcıdan olmalı")

    system = (SYSTEM + f"\nBugün: {datetime.now():%Y-%m-%d %H:%M}"
              + f"\nSon tarama: {_scan_status()['last_scan_finished'] or 'yok'}"
              + "\n\nKAYITLI KULLANICI TERCİHLERİ\n" + preferences.as_text())
    session = _Session(start_scan)
    client = GeminiClient(key, model=os.environ.get("GEMINI_CHAT_MODEL") or budget.chat_model()[0])
    client.purpose = "chat"
    reply = ""
    try:
        for rnd in range(MAX_ROUNDS):
            body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                    "tools": TOOLS, "generationConfig": {"temperature": 0.4}}
            if rnd == MAX_ROUNDS - 1:  # son tur: araç yok, eldekiyle cevap ver (döngü kırıcı)
                body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
                body["contents"] = contents + [{"role": "user", "parts": [{"text":
                    "(Sistem notu: araç kullanma hakkın bitti. Topladığın bilgilerle kullanıcıya ŞİMDİ "
                    "kısa bir Türkçe cevap yaz.)"}]}]
            r = client._post(body)
            if r.status_code != 200:
                raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            client.record_usage(data)
            cand = (data.get("candidates") or [{}])[0].get("content") or {"role": "model", "parts": []}
            parts = cand.get("parts") or []
            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            text = "".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought"))
            if not calls or rnd == MAX_ROUNDS - 1:
                reply = text.strip()
                break
            contents.append({"role": "model", "parts": parts})
            responses = []
            for fc in calls:
                log.info("Asistan tur %d: %s %s", rnd + 1, fc.get("name"),
                         json.dumps(fc.get("args") or {}, ensure_ascii=False)[:160])
                try:
                    res = session.run(fc.get("name", ""), fc.get("args") or {})
                except Exception as exc:  # aracın hatası sohbeti düşürmesin
                    log.exception("Asistan aracı hata: %s", fc.get("name"))
                    res = {"error": str(exc)[:200]}
                fr = {"name": fc.get("name"), "response": res}
                if fc.get("id"):
                    fr["id"] = fc["id"]
                responses.append({"functionResponse": fr})
            contents.append({"role": "user", "parts": responses})
    finally:
        client.close()
    if not reply:
        log.warning("Asistan metin cevabı üretmedi (%d arama, %d eylem)", session.searches, len(session.actions))
        if session.recs:
            reply = "Önerilerim aşağıda."
        elif session.actions:
            reply = "Tamam, not ettim. Devam edelim: başka neyi sever ya da sevmezsin, nasıl demliyorsun?"
        else:
            reply = "Bunu toparlayamadım, sorunu biraz daha kısa sorar mısın?"
    return {"reply": reply, "recommendations": session.recs, "actions": session.actions,
            "model": client.model, "tokens": [getattr(client, "total_in", 0), getattr(client, "total_out", 0)],
            "budget": budget.status()}

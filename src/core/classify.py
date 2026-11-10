"""Ürün açıklamasından kahve profili çıkarma (Gemini).

Girdi: ürün adı + marka + ürün sayfası açıklaması (src.scrapers.details).
Çıktı: kavrum, çekirdek türü, menşei, aroma notaları, asidite, gövde,
yoğunluk, uygun demleme yöntemleri — tavsiye asistanının kullanacağı yapı.

Kurallar (prompt'ta): bilgi öncelikle açıklamadan alınır; açıklamada yoksa ve
ürün çok bilinen bir ürünse genel bilgi kullanılabilir ama `source` alanında
belirtilir; emin olunmayan alan "bilinmiyor"/boş bırakılır (uydurma yok).

Anahtar: proje kökündeki `.env` dosyasında GEMINI_API_KEY=... (ya da ortam
değişkeni). Model: GEMINI_MODEL (varsayılan gemini-3.1-flash-lite).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import httpx

log = logging.getLogger(__name__)
# httpx her isteği INFO'da tam URL ile loglar; sessize al (gizli bilgi sızmasın)
logging.getLogger("httpx").setLevel(logging.WARNING)

API = "https://generativelanguage.googleapis.com/v1beta"
# Sınıflandırma: 2026-11 karşılaştırmasında (Pro referans) 3.1 Flash-Lite %89 uyum,
# ürün başı ~0,015 TL; Pro 10 kat pahalı. Aylık ~70 TL bütçe için Flash-Lite.
DEFAULT_MODEL = "gemini-3.1-flash-lite"
BATCH = 8            # tek istekte sınıflandırılan ürün
CALL_GAP_S = 7.0     # ücretsiz kota (dakikada ~10 istek) için istekler arası bekleme

ROASTS = ["açık", "orta", "orta-koyu", "koyu", "bilinmiyor"]
BEANS = ["arabica", "arabica-robusta", "robusta", "bilinmiyor"]
LEVELS3 = ["düşük", "orta", "yüksek", "bilinmiyor"]
BODIES = ["hafif", "orta", "dolgun", "bilinmiyor"]
BREWS = ["espresso", "moka", "filtre", "french_press", "turk", "otomatik_makine"]
SOURCES = ["açıklama", "açıklama+genel_bilgi", "genel_bilgi"]

SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "roast": {"type": "STRING", "enum": ROASTS},
            "bean": {"type": "STRING", "enum": BEANS},
            "arabica_pct": {"type": "INTEGER", "nullable": True},
            "origin": {"type": "ARRAY", "items": {"type": "STRING"}},
            "single_origin": {"type": "BOOLEAN", "nullable": True},
            "flavor_notes": {"type": "ARRAY", "items": {"type": "STRING"}},
            "acidity": {"type": "STRING", "enum": LEVELS3},
            "body": {"type": "STRING", "enum": BODIES},
            "intensity": {"type": "INTEGER", "nullable": True},
            "brew_methods": {"type": "ARRAY", "items": {"type": "STRING", "enum": BREWS}},
            "decaf": {"type": "BOOLEAN"},
            "source": {"type": "STRING", "enum": SOURCES},
            "summary": {"type": "STRING"},
        },
        "required": ["id", "roast", "bean", "origin", "flavor_notes", "acidity", "body",
                     "brew_methods", "decaf", "source", "summary"],
    },
}

PROMPT = """Sen bir kahve uzmanısın. Aşağıdaki çekirdek kahve ürünlerinin her biri için,
verilen ürün adı ve ürün sayfası açıklamasından bir kahve profili çıkar.

Kurallar:
- Bilgiyi ÖNCELİKLE açıklamadan al. Açıklamada olmayan bir alanı, yalnızca ürün
  çok bilinen bir ürünse (ör. Lavazza Qualità Oro, illy Classico) genel bilginle
  doldurabilirsin; o zaman source="açıklama+genel_bilgi" (ya da açıklama boşsa
  "genel_bilgi") yaz.
- Emin olmadığın alanı UYDURMA: "bilinmiyor", null ya da boş liste bırak.
- flavor_notes: Türkçe, küçük harf, kısa (ör. "çikolata", "karamel", "fındık",
  "meyvemsi", "narenciye", "çiçeksi", "baharatlı", "bal", "kakao", "orman meyvesi").
- origin: çekirdeğin YETİŞTİĞİ ülke/bölge, Türkçe (ör. "Brezilya", "Etiyopya", "Afrika");
  harmanda birden çok olabilir. Kavurma/paketleme yeri DEĞİLDİR ("Menşei İstanbul",
  "Almanya menşeli" gibi ifadeler kavurucunun yeridir — bunları origin'e yazma).
- intensity: 1 (yumuşak) – 5 (çok yoğun) ölçeğine dönüştür; marka 1–10 ölçeği
  veriyorsa ikiye böl ve yuvarla. Bilinmiyorsa null.
- brew_methods: açıklamada geçen ya da kavrum/yapıya göre makul olan yöntemler;
  espresso harmanları için "espresso" ve "moka" uygundur.
- summary: tek cümlelik Türkçe özet (ör. "Orta kavrum, Brezilya ağırlıklı, çikolata
  ve fındık notalı yumuşak bir espresso harmanı").
- Her ürün için verilen id'yi aynen geri yaz.

Ürünler (JSON):
"""


def load_api_key(root: Optional[Path] = None) -> Optional[str]:
    """Ortam değişkeni ya da proje kökündeki .env'den GEMINI_API_KEY."""
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key.strip()
    root = root or Path(__file__).resolve().parents[2]
    for name in (".env", ".env.txt"):
        f = root / name
        if not f.exists():
            continue
        lines = [l.strip() for l in f.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
                 if l.strip() and not l.strip().startswith("#")]
        for line in lines:
            k, sep, v = line.partition("=")
            if sep and k.strip() == "GEMINI_API_KEY":
                return v.strip().strip('"').strip("'") or None
        # Dosyada yalnız anahtarın kendisi yazılıysa (KEY=değer biçimi olmadan)
        if len(lines) == 1 and "=" not in lines[0] and " " not in lines[0] and len(lines[0]) >= 20:
            return lines[0].strip('"').strip("'")
    return None


_TEMP = re.compile(r"(\d{3})\s*°\s*([FC])", re.IGNORECASE)


def roast_from_name(name: str) -> Optional[str]:
    """Addaki kavurma sıcaklığından kavrum (The Whirl: 423°F, 441°F ...).
    Yaygın aralıklar: <410°F açık, 410–435 orta, 436–455 orta-koyu, >455 koyu."""
    m = _TEMP.search(name or "")
    if not m:
        return None
    t = int(m.group(1))
    f = t * 9 / 5 + 32 if m.group(2).upper() == "C" else t
    if not 350 <= f <= 500:
        return None
    return "açık" if f < 410 else "orta" if f <= 435 else "orta-koyu" if f <= 455 else "koyu"


def normalize(p: dict) -> dict:
    """Model çıktısını güvenli değerlere sıkıştır (enum dışı → bilinmiyor)."""
    def pick(v, allowed):
        return v if v in allowed else "bilinmiyor"

    intensity = p.get("intensity")
    if isinstance(intensity, (int, float)):
        intensity = max(1, min(5, round(intensity)))
    else:
        intensity = None
    pct = p.get("arabica_pct")
    pct = int(pct) if isinstance(pct, (int, float)) and 0 < pct <= 100 else None
    return {
        "roast": pick(p.get("roast"), ROASTS),
        "bean": pick(p.get("bean"), BEANS),
        "arabica_pct": pct,
        "origin": [str(o).strip() for o in (p.get("origin") or []) if str(o).strip()][:6],
        "single_origin": p.get("single_origin") if isinstance(p.get("single_origin"), bool) else None,
        "flavor_notes": [str(n).strip().lower() for n in (p.get("flavor_notes") or []) if str(n).strip()][:8],
        "acidity": pick(p.get("acidity"), LEVELS3),
        "body": pick(p.get("body"), BODIES),
        "intensity": intensity,
        "brew_methods": [b for b in (p.get("brew_methods") or []) if b in BREWS],
        "decaf": bool(p.get("decaf")),
        "source": p.get("source") if p.get("source") in SOURCES else "açıklama",
        "summary": str(p.get("summary") or "").strip()[:300],
    }


class GeminiClient:
    def __init__(self, api_key: str, model: Optional[str] = None, timeout: float = 90.0) -> None:
        self.key = api_key
        self.model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
        # Anahtar URL'de değil başlıkta: httpx istek URL'lerini log'a yazar
        self.http = httpx.Client(timeout=timeout, headers={"x-goog-api-key": api_key})

    def close(self) -> None:
        self.http.close()

    # --- kullanım (maliyet) takibi -------------------------------------------
    usage_sink = None  # callable(client, input_tokens, output_tokens) — backend bağlar
    purpose = "other"  # kullanım kaydında amaç etiketi (classify / chat)

    def record_usage(self, data: dict) -> None:
        u = data.get("usageMetadata") or {}
        tin = int(u.get("promptTokenCount") or 0)
        tout = int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0)
        self.last_usage = (tin, tout)
        self.total_in = getattr(self, "total_in", 0) + tin
        self.total_out = getattr(self, "total_out", 0) + tout
        if GeminiClient.usage_sink:
            try:
                GeminiClient.usage_sink(self, tin, tout)
            except Exception:
                log.exception("Kullanım kaydı yazılamadı")

    def _post(self, body: dict) -> httpx.Response:
        return self.http.post(
            f"{API}/models/{self.model}:generateContent",
            json=body,
        )

    def _fallback_model(self) -> Optional[str]:
        """Varsayılan model yoksa hesapta erişilebilir bir 'flash' modeli seç."""
        r = self.http.get(f"{API}/models", params={"pageSize": 200})
        if r.status_code != 200:
            return None
        names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        flash = sorted([n for n in names if "flash" in n and "lite" not in n
                        and "preview" not in n and "exp" not in n], reverse=True)
        return flash[0] if flash else (names[0] if names else None)

    def generate_json(
        self,
        prompt: Optional[str],
        schema: dict,
        *,
        system: Optional[str] = None,
        contents: Optional[list] = None,
        temperature: float = 0,
        thinking: Optional[dict] = None,
    ) -> list | dict:
        """Tek mesaj (prompt) ya da çok turlu sohbet (contents + system) → JSON."""
        body = {
            "contents": contents or [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if thinking:
            body["generationConfig"]["thinkingConfig"] = thinking
        for attempt in range(3):
            r = self._post(body)
            if r.status_code == 404 and attempt == 0:
                alt = self._fallback_model()
                if alt and alt != self.model:
                    log.warning("Gemini modeli %s yok, %s kullanılıyor", self.model, alt)
                    self.model = alt
                    continue
            if r.status_code in (429, 500, 503):
                time.sleep(30 * (attempt + 1))
                continue
            if r.status_code != 200:
                raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            self.record_usage(data)
            try:
                text = next(p["text"] for p in data["candidates"][0]["content"]["parts"] if "text" in p)
            except (KeyError, IndexError, StopIteration) as exc:
                raise RuntimeError(f"Gemini boş yanıt: {json.dumps(data)[:300]}") from exc
            return json.loads(text)
        raise RuntimeError(f"Gemini yanıt vermedi (HTTP {r.status_code})")


def classify_batch(client: GeminiClient, items: list[dict]) -> dict[str, dict]:
    """items: [{id, name, brand, description}] -> id -> normalize edilmiş profil."""
    payload = json.dumps(items, ensure_ascii=False)
    result = client.generate_json(PROMPT + payload, SCHEMA)
    out: dict[str, dict] = {}
    for p in result if isinstance(result, list) else []:
        pid = str(p.get("id", ""))
        if pid:
            out[pid] = normalize(p)
    return out


def classify_pending(db_path: str, limit: int = 80, allow=None) -> dict:
    """Açıklaması olup profili olmayan ürünleri sınıflandır. Senkron (thread'de çalıştır)."""
    from src.storage.db import PriceDatabase

    key = load_api_key()
    if not key:
        return {"status": "no_key", "classified": 0}
    db = PriceDatabase(db_path)
    client = GeminiClient(key)
    client.purpose = "classify"
    done, errors = 0, []
    try:
        rows = db.details_to_classify(limit)
        for i in range(0, len(rows), BATCH):
            if allow is not None and not allow():
                errors.append("aylık yapay zekâ bütçesinin sınıflandırma payı doldu")
                break
            chunk = rows[i:i + BATCH]
            items = [{"id": str(n), "name": name, "brand": brand, "description": desc}
                     for n, (_url, name, brand, desc) in enumerate(chunk)]
            try:
                profiles = classify_batch(client, items)
            except Exception as exc:
                log.warning("Gemini sınıflandırma hatası: %s", exc)
                errors.append(str(exc)[:200])
                break  # kota/anahtar sorunu büyük ihtimal; sonraki çalıştırmada devam
            for n, (url, name, *_rest) in enumerate(chunk):
                prof = profiles.get(str(n))
                if prof and prof["roast"] == "bilinmiyor" and roast_from_name(name):
                    prof["roast"] = roast_from_name(name)  # addaki kavurma sıcaklığından
                if prof:
                    db.save_profile(url, json.dumps(prof, ensure_ascii=False), client.model)
                    done += 1
            if i + BATCH < len(rows):
                time.sleep(CALL_GAP_S)
    finally:
        client.close()
        db.close()
    log.info("Gemini: %d ürün profili çıkarıldı (%s)", done, client.model)
    return {"status": "ok" if not errors else "error", "classified": done,
            "model": client.model, "errors": errors}

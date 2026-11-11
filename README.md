# Coffee Deal Tracker

Trendyol, Hepsiburada ve Amazon.com.tr'de kahve markalarını (Lavazza, illy, Meinl, Tchibo, Whirl vb.) her gün tarayıp **gerçek** fırsatları bulan, dönemin fiyat normunu çıkaran ve yapay zekâ (Gemini) destekli bir **kahve asistanıyla** sana uygun çekirdeği öneren uygulama.

Tek bir tarama çekirdeğini (`src/core/scan_engine.py`) paylaşan üç istemcisi vardır:
**masaüstü** (`desktop.py` — web arayüzünü kendi penceresinde gösteren wrapper), **web** (tarayıcı / telefona kurulabilen PWA) ve **API** (FastAPI backend).

- **Dil/Framework**: Python 3.12+ · FastAPI · React + Vite + Tailwind · Playwright · SQLite · PySide6 (QtWebEngine wrapper) · Google Gemini API
- **Arkaplan**: Backend 7/24 çalışır (PC'de veya bulutta) → APScheduler ile her gün otomatik tarama, kaçırılan taramanın telafisi ve fiyat alarmı takibi.

## Özellikler

### Fırsat tespiti
- **İki yönlü tespit**: fiyat son N günün (varsayılan 90) en düşüğünün altına indi mi, ya da sitede üstü çizili eski fiyat var mı?
- **Sahte indirim elemesi**: Sitelerin "eski fiyat"ı keyfi olabiliyor (aylardır süren kalıcı "%40 indirim" etiketi, 1 günlük fiyat sıçratıp geri düşürme). TR mevzuatındaki yaklaşımla aynı kural uygulanır: referans fiyat **indirimden önceki 30 günün en düşüğüdür**. Her fırsat `gerçek` / `doğrulanamadı` (yeterli geçmiş yok) / `sahte` olarak etiketlenir; sahte olanlar ayrı sekmede listelenir.
- **Aykırı fiyat koruması**: Ayrıştırma hatasından doğan saçma fiyatlar (ör. "%99 indirim") geçmişi bozmaz.

### Fiyat analizi
- **Gramaj ve kilo fiyatı**: Ürün adından paket boyu okunur ("1 kg", "4 x 250 gr", "1 kg | 2'li Paket" → 2 kg) ve her ürün için TL/kg hesaplanır. Tabloda gramaj kovalarıyla (≤250 g, 500 g, 1 kg, 2 kg+) filtreleme.
- **Piyasa sekmesi (dönemin normu)**: "Orta kalite 1 kg kahve şu an kaç lira?" sorusunun cevabı. Paket boyuna göre aylık kilo fiyatı medyanı ve ucuz / orta / pahalı dilim sınırları (çeyrekler), marka bazında karşılaştırma. Her ürüne son 30 günün normuna göre **piyasa konumu** etiketi eklenir.
- **Fiyat geçmişi grafiği**: Her ürün için 90 günlük çizgi grafik.
- **Fiyat alarmı**: Bir ürüne hedef fiyat koy; tarama sonrası fiyat altına inince tetiklenir (opsiyonel e-posta).
- **Veri dışa aktarma** (⬇ Dışa aktar): fiyat geçmişi / ürünler / fırsatlar → CSV, Excel (.xlsx) veya JSON; pandas ve Excel pivot için "tidy" formatta.

### Yapay zekâ (Gemini)

> 🔑 **Bu bölümdeki özellikler kendi Gemini API anahtarını gerektirir.** Repoda anahtar yoktur; her kullanıcı kendi anahtarını bağlar ve kullanım ücreti kendi Google hesabından düşer. Kurulum: [Gemini API anahtarı](#gemini-api-anahtarı-yapay-zekâ-özellikleri-için). Anahtar olmadan da tarama, fırsatlar, sahte indirim elemesi, Piyasa sekmesi ve dışa aktarma tamamen çalışır.
- **Ürün profilleri**: Her taramada site başına 10 yeni ürünün sayfa açıklaması çekilir; tarama bitince Gemini bunlardan **kavrum, tat notaları, menşe, çekirdek türü, gövde/asidite ve uygun demleme yöntemlerini** çıkarır (her ürün yalnız bir kez işlenir).
- **☕ Kahve Asistanı**: Sağdan açılan sohbet paneli. Demleme yöntemini ve tat tercihini sorar, güncel katalogdan kart halinde öneri yapar (fiyat, kilo fiyatı, piyasa konumu, indirimin gerçek/sahte olduğu). Araç çağırarak:
  - katalogda arama, marka ve piyasa özeti çıkarma,
  - **ayarları değiştirme** (marka ekle/çıkar, site, ürün türü, otomatik tarama saati),
  - **anlık tarama başlatma** ve durumunu izleme,
  - sevdiğin / sevmediğin kahveleri **kalıcı olarak hatırlama** (panelde 📝 ile görüntüle/sil).
- **Bütçe kontrolü**: Her Gemini çağrısının maliyeti kaydedilir. AI Studio bakiyesi belirlenen bitiş tarihine kadar aylara yayılır (kullanılmayan pay devreder); ayın payının yarısı dolunca sohbet daha ucuz modele geçer, pay dolunca durur. Panelde 💳 ile güncel bakiye girildikçe maliyet tahmini gerçek faturaya göre kendini düzeltir.

### Kullanım kolaylıkları
- **Sonuçlarda arama** ve sütun başlığına tıklayarak sıralama (fiyat/indirim gerçek değere göre).
- **Özelleştirilebilir filtreler (⚙ Filtreler)**: marka listesi, ürün türleri (çekirdek / öğütülmüş / kapsül / filtre / türk / granül — varsayılan yalnız çekirdek), indirim penceresi, zamanlanmış tarama.
- **Ürün türü ayrımı**: Kahve markalarının sattığı çikolata, gofret, fincan vb. ile toz/çekilmiş kahve ve 2'si 1 arada ürünler çekirdek sayılmaz.
- **Kaçırılan taramayı telafi**: PC o saatte kapalı/uykudaysa günlük tarama, PC açılınca yapılır.
- **Kalıcı snapshot**: Uygulama açıldığında son taramanın sonuçları yeniden tarama gerektirmeden görünür.
- **Bot koruma toleransı**: Site başına izole tarayıcı context'i; Amazon'un AWS WAF challenge'ı için ısınma; bir site bloklansa bile diğerleri etkilenmez.

---

## Kurulum (geliştirici)

```powershell
pip install -r requirements.txt
python -m playwright install chromium
npm --prefix frontend install
npm --prefix frontend run build
```

### Gemini API anahtarı (yapay zekâ özellikleri için)

Yapay zekâ özellikleri (ürün profilleri ve ☕ Kahve Asistanı) isteğe bağlıdır. **Repo hiçbir API anahtarı içermez; asistanı kullanmak isteyen herkes kendi anahtarını eklemelidir.** Gemini çağrılarının ücreti anahtarın sahibinin Google hesabından düşer.

Anahtar yoksa:
- Asistan panelinde **"Gemini anahtarı bulunamadı (.env)."** uyarısı görünür, sohbet çalışmaz.
- Taramalardan sonra ürün profili çıkarılmaz (ürün açıklamaları yine kaydedilir; anahtar eklenince sonraki taramada işlenir).
- Uygulamanın geri kalanı (tarama, fırsatlar, sahte indirim, Piyasa, alarmlar, dışa aktarma) normal çalışır.

1. [Google AI Studio](https://aistudio.google.com/)'dan bir API anahtarı al.
2. Proje kökünde `.env` dosyası oluştur:
   ```
   GEMINI_API_KEY=anahtarın
   ```
   (Dosyada yalnızca anahtarın kendisinin olması da kabul edilir. `.env` gitignore'dadır — **asla commit'leme**.)
3. İsteğe bağlı model geçersiz kılma: `GEMINI_MODEL` (sınıflandırma, varsayılan `gemini-3.1-flash-lite`), `GEMINI_CHAT_MODEL` (sohbet; varsayılan bütçeye göre `gemini-3.8-flash` → `gemini-3.1-flash-lite`).

Anahtar istek başlığında (`x-goog-api-key`) gönderilir; URL'ye ve log'lara yazılmaz.

**Bütçe dosyası** — `data/ai_wallet.json` (gitignore'da). İlk kayıtta bitiş tarihi gerektiği için asistana söyleyerek ("bakiyem 500 TL, Ağustos sonuna kadar yetsin") ya da `POST /api/ai/balance` ile `{"balance_try": 500, "until": "2027-08-31"}` göndererek oluşturulur; sonraki güncellemeler paneldeki 💳 ile yapılabilir:

```json
{ "balance_try": 664.08, "balance_at": "2026-11-10T07:37:32", "until": "2027-08-31", "cost_factor": 1.3 }
```

| Alan | Açıklama |
|---|---|
| `balance_try` / `balance_at` | AI Studio'daki bakiye ve okunduğu an |
| `until` | Paranın yetmesi gereken son gün |
| `cost_factor` | Takip edilen maliyet × katsayı = tahmini gerçek fatura. Bakiye en az 3 gün arayla güncellendikçe otomatik düzelir |

Dosya yoksa aylık sabit 60 TL sınır uygulanır.

### Masaüstü uygulaması

```powershell
.\run.ps1
```

`run.ps1` gerekirse frontend'i derler, sonra `desktop.py`'yi çalıştırır: backend arka planda başlar ve arayüz QtWebEngine penceresinde açılır. Paketli sürüm (`KahveTakip.spec` → `dist/KahveTakip.exe`) arayüzü çalışan backend'den yükler; frontend/backend değişiklikleri için exe'yi yeniden derlemek gerekmez, pencereyi kapatıp açmak yeter.

### Backend'i PC'de 7/24 çalıştırma (Windows)

`start_backend.vbs` backend'i penceresiz başlatır (çıktı `data/backend.log`'a). Bir kopyasını
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` klasörüne koyarsan her oturum açılışında otomatik başlar. Dosyadaki proje yolunu kendi konumuna göre düzenle.

---

## Web Platformu (backend + frontend)

- **`backend/`** — FastAPI (REST + WebSocket). Fırsatlar, ürünler, fiyat geçmişi, piyasa normu, alarmlar, dışa aktarma, zamanlanmış tarama ve kahve asistanı.
- **`frontend/`** — React + Vite + Tailwind (PWA). Canlı tarama ilerlemesi WebSocket ile.

### Docker ile

```bash
docker compose up --build
```

- Frontend: `http://localhost:5173`
- API + Swagger: `http://localhost:8000/docs`

### Docker olmadan (geliştirme)

```powershell
# 1) Backend
py -3.14 -m uvicorn backend.main:app --reload --port 8000
# 2) Frontend (ayrı terminal)
npm --prefix frontend run dev    # http://localhost:5173
```

> Windows'ta `localhost` bazen IPv6'ya gider; sorun olursa `http://127.0.0.1:8000` kullan.

### API özeti

| Uç nokta | İşlev |
|---|---|
| `GET /api/deals`, `GET /api/products` | Son snapshot (piyasa konumu ve kahve profiliyle) |
| `GET /api/history?url=` | Ürünün fiyat geçmişi |
| `GET /api/market?size=250\|500\|1000\|2000` | Dönemin normu: aylık kilo fiyatı dilimleri, marka karşılaştırması |
| `GET /api/export?dataset=history\|products\|deals\|all&format=csv\|xlsx\|json&days=` | Dışa aktarma |
| `GET/PUT /api/config` | Ayarlar |
| `POST /api/scan`, `POST /api/scan/cancel`, `GET /api/scan`, `WS /ws/scan` | Tarama başlat / iptal / durum / canlı ilerleme |
| `GET /api/schedule` | Bir sonraki otomatik tarama |
| `GET/POST/DELETE /api/alerts` | Fiyat alarmları |
| `POST /api/chat` | Kahve asistanı (`{messages: [{role, text}]}`) |
| `GET /api/ai` | Yapay zekâ bütçesi + profil kapsamı |
| `POST /api/ai/balance` | AI Studio bakiyesini güncelle (`{balance_try, until?}`) |
| `GET/DELETE /api/ai/preferences` | Asistanın hatırladığı tercihler |
| `GET/POST /api/enrich` | Ürün profili durumu / profil çıkarmayı elle başlat |

### CI

`.github/workflows/ci.yml` her push/PR'da: backend derleme + `pytest`, frontend `tsc` + Vite build ve iki Docker imajının build'ini çalıştırır. Testler Gemini'yi çağırmaz.

### Fiyat alarmı e-postası (opsiyonel)

Şu ortam değişkenleri ayarlıysa tetiklenen alarmlar e-posta ile de bildirilir:
`CDT_SMTP_HOST`, `CDT_SMTP_PORT`, `CDT_SMTP_USER`, `CDT_SMTP_PASS`, `CDT_ALERT_TO`.

### Yeni site / marka / kategori ekleme

- **Marka & ürün türü:** `config.json`, ⚙ Filtreler ya da asistana "şu markayı da takip et" demek yeterli.
- **Yeni site:** `src/scrapers/_template.py`'yi kopyalayıp seçicileri doldurun, `register_default_scrapers()`'a ekleyin, `sites`'a adını yazın. Ürün açıklaması çekmek için `src/scrapers/details.py` → `SELECTORS`'a sitenin açıklama seçicisini ekleyin.

### Dağıtım (deploy)

- **PC:** yukarıdaki Startup VBS yöntemi (şu an kullanılan).
- **VPS:** sunucuda repoyu çekip `docker compose up -d`.
- **PaaS:** `render.yaml` bir Render.com blueprint taslağıdır. Fly.io / Railway de Docker imajlarıyla çalışır.

---

## Yapılandırma (`config.json`)

```json
{
  "brands": ["lavazza", "illy", "meinl", "tchibo", "kicking horse", "kahve dünyası", "jacobs", "whirl"],
  "sites": ["trendyol", "hepsiburada", "amazon_tr"],
  "history_days": 90,
  "max_products_per_brand_per_site": 15,
  "request_delay_ms": 2000,
  "headless": true,
  "search_suffix": "kahve çekirdeği",
  "product_types": ["cekirdek"],
  "start_with_windows": true,
  "auto_scan_on_launch": true,
  "schedule_enabled": true,
  "schedule_time": "10:00",
  "usd_try": 50.0
}
```

| Alan | Açıklama |
|---|---|
| `brands` | Her sitede aranacak markalar (küçük harf). Ürün adı bu stringi içermiyorsa elenir. |
| `sites` | `trendyol`, `hepsiburada`, `amazon_tr`. Kayıtlı olmayan site adı atlanır. |
| `history_days` | "Son X günün en düşüğü" penceresi (varsayılan 90). |
| `max_products_per_brand_per_site` | Marka × site başına üst sınır. |
| `request_delay_ms` | İstekler arası bekleme (bot engellemeyi azaltır). |
| `headless` | `false` yaparsanız tarayıcı görünür olur. |
| `search_suffix` | Arama sorgusuna eklenen kelime (ör. `"meinl kahve çekirdeği"`). Çekirdek dışı türler de seçilince otomatik olarak genel `"kahve"` aramasına geçilir. |
| `product_types` | `cekirdek`, `ogutulmus`, `kapsul`, `filtre`, `turk`, `instant`. Varsayılan yalnız `cekirdek`. |
| `start_with_windows` | Masaüstü uygulamasını Windows oturum açılışında başlat (`HKCU\...\Run`). |
| `auto_scan_on_launch` | O gün masaüstü uygulaması ilk açıldığında tarama başlat (günde en fazla bir kez). |
| `schedule_enabled` / `schedule_time` | Backend'in her gün `HH:MM`'de otomatik taraması; kaçırılırsa PC açılınca telafi edilir. |
| `usd_try` | Gemini maliyetini TL'ye çevirmek için dolar kuru. |

> Ayarların çoğu **⚙ Filtreler** penceresinden ya da kahve asistanından değiştirilebilir; `config.json` güncellenir. `exe` yanındaki `config.json` önceliklidir.

---

## Nasıl çalışır?

1. Backend her gün belirlenen saatte (veya **Taramayı Başlat** / asistan ile) tarama yapar: seçili her site × marka için Playwright headless Chromium arama sonuçlarını okur.
2. Ürünler türüne göre süzülür (çekirdek mi, öğütülmüş mü, kahve mi bile değil mi), ad/fiyat/üstü çizili fiyat/gramaj `data/price_history.db` (SQLite) içine yazılır.
3. Site başına 10 yeni ürünün sayfa açıklaması çekilir; tarama bitince Gemini bunlardan kahve profili çıkarır (bütçe izin verdiği ölçüde).
4. Her ürün için fırsat kararı verilir: 90 günlük yeni dip mi, sayfadaki indirim 30 günlük en düşüğe göre gerçek mi?
5. Arayüz son 48 saatin snapshot'ını gösterir: **Fırsatlar**, **Sahte İndirimler**, **Tüm Ürünler**, **Piyasa** sekmeleri; ürün satırından 📈 grafik.
6. **☕ Asistan** bu katalog, piyasa normu, ürün profilleri ve senin kayıtlı tercihlerinle öneri yapar.

### İlk gün problemi

İlk taramalarda geçmiş olmadığından geçmiş bazlı fırsatlar ve indirim doğrulaması çalışmaz; sitede indirim gösteren ürünler "doğrulanamadı" etiketiyle listelenir. Birkaç günlük taramadan sonra (30 günde en az 5 kayıt) doğrulama devreye girer.

---

## Bilinen Sınırlamalar

| Site | Durum |
|---|---|
| Trendyol | ✅ Stabil (TR ve EN sayı biçimleri okunuyor) |
| Amazon.com.tr | ✅ Stabil (AWS WAF challenge için oturum ısınması yapılıyor) |
| Hepsiburada | ✅ Çalışıyor; bot koruması agresif, ara sıra "Güvenlik" sayfası dönebilir |

- Siteler HTML yapılarını değiştirdiğinde ilgili scraper (`src/scrapers/<site>.py`) güncellenmelidir.
- Ürün profilleri satıcının yazdığı açıklamaya dayanır; açıklama eksik/yanlışsa profil de öyle olur. Kapsam taramalarla kademeli artar.
- Gemini model fiyatları `backend/budget.py` → `PRICES` tablosundadır; Google fiyat değiştirirse güncellenmelidir.

---

## Proje Yapısı

```
coffee-deal-tracker/
├── config.json              # markalar, siteler, ayarlar (tek kaynak)
├── .env                     # GEMINI_API_KEY (gitignore'da, sen oluşturursun)
├── requirements.txt
├── run.ps1                  # masaüstü uygulamasını çalıştır
├── desktop.py               # MASAÜSTÜ wrapper: backend + QtWebEngine penceresi
├── KahveTakip.spec          # PyInstaller → dist/KahveTakip.exe
├── start_backend.vbs        # backend'i penceresiz başlat (Startup klasörü için)
├── docker-compose.yml · render.yaml
├── src/                     # PAYLAŞILAN ÇEKİRDEK (UI yok)
│   ├── core/
│   │   ├── scan_engine.py   # run_scan() — tarama beyni (+ ürün açıklaması çekme)
│   │   ├── deal_detector.py # fırsat + sahte indirim (30 gün referans) mantığı
│   │   ├── weight.py        # ürün adından gramaj / paket sayısı
│   │   ├── classify.py      # Gemini istemcisi + ürün profili çıkarma
│   │   ├── config.py        # AppConfig + PRODUCT_TYPES
│   │   └── models.py
│   ├── scrapers/
│   │   ├── base.py          # BaseScraper + ürün türü sınıflandırma
│   │   ├── trendyol.py · hepsiburada.py · amazon_tr.py
│   │   ├── details.py       # ürün sayfası açıklaması çekme
│   │   └── _template.py     # yeni site şablonu
│   └── storage/db.py        # SQLite (ürün, fiyat geçmişi, alarm, açıklama/profil, AI kullanımı)
├── backend/                 # FastAPI (REST + WebSocket + APScheduler)
│   ├── main.py · scan_manager.py · scheduler.py · services.py · notify.py · schemas.py
│   ├── market.py            # dönemin normu (kilo fiyatı dilimleri)
│   ├── export.py            # CSV / Excel / JSON dışa aktarma
│   ├── enrich.py            # tarama sonrası Gemini profil çıkarma
│   ├── assistant.py         # kahve asistanı (araç çağıran Gemini sohbeti)
│   ├── budget.py            # AI maliyet takibi + bakiyeyi tarihe yayan bütçe
│   ├── preferences.py       # asistanın hatırladığı kullanıcı tercihleri
│   └── Dockerfile · tests/
├── frontend/                # React + Vite + Tailwind (PWA)
│   └── src/ (App.tsx, api.ts, components/: MarketView, AssistantPanel, …)
└── data/                    # otomatik oluşur (gitignore'da)
    ├── price_history.db     # fiyatlar, açıklamalar, profiller, AI kullanımı
    ├── ai_wallet.json       # AI bakiyesi / bütçe planı
    ├── ai_preferences.json  # asistanın hafızası
    └── backend.log
```

---

## Test

```powershell
py -3.14 -m pytest -q backend/tests
```

### Scraper'ı elle test etme

```powershell
python -m src.scrapers.trendyol meinl
python -m src.scrapers.amazon_tr tchibo
python -m src.scrapers.hepsiburada lavazza
```

Her modül `__main__` bloğu içerir; marka argümanıyla çağrıldığında bulunan ürünleri konsola döker.

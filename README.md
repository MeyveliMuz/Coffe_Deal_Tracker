# Coffee Deal Tracker

Trendyol, Hepsiburada ve Amazon.com.tr sitelerinde kaliteli kahve markalarını (Meinl, Tchibo, Lavazza vb.) tarayıp fırsatları bulan bir Windows masaüstü uygulaması. Hem kendi geçmiş fiyatına göre düşüşleri, hem de site üzerinde gösterilen indirimleri tespit eder.

- **Dil/Framework**: Python 3.11+ · PySide6 · Playwright · SQLite
- **Bildirim**: Yalnızca uygulama içinde (Windows toast / e-posta / Telegram yok)
- **Arkaplan**: Yok — pencere kapatıldığında her şey durur

## Özellikler

- **İki yönlü fırsat tespiti**:
  - Geçmiş bazlı: Fiyat son N günün en düşüğünün altına indi mi?
  - Site bazlı: Üründe üstü çizili eski fiyat (strikethrough) gösteriliyor mu?
- **Sonuçlarda arama**: Tablonun üstündeki 🔍 kutuyla marka/ürün/site bazında anlık filtreleme.
- **Özelleştirilebilir filtreler (⚙ Filtreler)**: Popüler marka listesinden kutucukla seçim + serbest metinle kendi markanı ekleme; ürün türü kategorileri (çekirdek/öğütülmüş/kapsül/filtre/türk/granül — varsayılan yalnızca çekirdek); ayarlanabilir indirim penceresi (varsayılan 90 gün).
- **Otomatik başlatma**: Windows oturum açılışında başlatma ve/veya o günkü ilk açılışta otomatik tarama (günde en fazla bir kez; ⚙ Filtreler'den açılır).
- **Fiyat geçmişi grafiği**: Her ürün için 90 günlük çizgi grafik. Node'a hover/tıkla → fiyat + tarih tooltip'i.
- **Akıllı sütunlar (Fırsatlar)**: Şu anki Fiyat · İndirimsiz Fiyat (site strike) · Önceki Fiyat (son değişim öncesi) · İndirim %.
- **Sayısal sıralama**: Fiyat / İndirim sütunları gerçek değere göre sıralanır.
- **Kalıcı snapshot**: Uygulama kapanıp açıldığında son taramadaki fırsatlar yeniden tarama gerektirmeden görünür.
- **Bot koruma toleransı**: Site başına izole tarayıcı context'i; bir site bloklansa bile diğerleri etkilenmez.

---

## Kurulum (geliştirici)

```powershell
cd <repo-kökü>
pip install -r requirements.txt
python -m playwright install chromium
```

Çalıştırma:

```powershell
.\run.ps1
```

veya:

```powershell
python src/main.py
```

---

## Paketleme (.exe oluşturma)

```powershell
.\build.ps1
```

Çıktı: `dist\CoffeeDealTracker\CoffeeDealTracker.exe`

İlk açılışta Playwright Chromium `%LOCALAPPDATA%\ms-playwright` altına indirilir (~150 MB). Sonraki açılışlar hızlıdır.

---

## Web Platformu (backend + frontend)

Masaüstü (Qt) uygulamasının yanında, aynı tarama çekirdeğini (`src/core/scan_engine.py`) paylaşan bir **web yığını** vardır:

- **`backend/`** — FastAPI (REST + WebSocket). Fırsatlar, ürünler, fiyat geçmişi, fiyat alarmları ve zamanlanmış tarama.
- **`frontend/`** — React + Vite + Tailwind. Modern arayüz; canlı tarama ilerlemesi WebSocket ile.

### Docker ile (önerilen)

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
npm --prefix frontend install   # ilk kez
npm --prefix frontend run dev    # http://localhost:5173
```

### CI

`.github/workflows/ci.yml` her push/PR'da: backend derleme + `pytest`, frontend `tsc` + Vite build, ve iki Docker imajının build'ini çalıştırır.

### Fiyat alarmı e-postası (opsiyonel)

Şu ortam değişkenleri ayarlıysa tetiklenen alarmlar e-posta ile de bildirilir (yoksa yalnızca uygulama içi):
`CDT_SMTP_HOST`, `CDT_SMTP_PORT`, `CDT_SMTP_USER`, `CDT_SMTP_PASS`, `CDT_ALERT_TO`.

### Yeni site / marka / kategori ekleme

- **Marka & ürün türü:** Tamamen serbesttir — `config.json` (veya ⚙ Filtreler) üzerinden istediğiniz markaları ve ürün türlerini (`cekirdek`, `ogutulmus`, `kapsul`, `filtre`, `turk`, `instant`) seçersiniz. Mimari kahveye özel değildir; suffix'i değiştirip başka kategorilere de uyarlanabilir.
- **Yeni site:** `src/scrapers/_template.py`'yi kopyalayıp seçicileri doldurun, `register_default_scrapers()`'a ekleyin, `sites`'a adını yazın. Çekirdek (tarama motoru, DB, UI) hiç değişmez — yatay büyüme.

### Dağıtım (deploy)

- **VPS (en basit, gerçek):** Sunucuda repoyu çekip `docker compose up -d`.
- **PaaS:** `render.yaml` bir Render.com blueprint taslağıdır (backend + frontend). Fly.io / Railway de Docker imajlarıyla çalışır.

---

## Yapılandırma (`config.json`)

```json
{
  "brands": ["meinl", "tchibo", "whirl", "lavazza", "illy", "kicking horse"],
  "sites": ["trendyol", "hepsiburada", "amazon_tr"],
  "history_days": 90,
  "max_products_per_brand_per_site": 15,
  "request_delay_ms": 2000,
  "headless": true,
  "search_suffix": "kahve çekirdeği",
  "product_types": ["cekirdek"],
  "start_with_windows": false,
  "auto_scan_on_launch": false
}
```

| Alan | Açıklama |
|---|---|
| `brands` | Her sitede aranacak markalar (küçük harf). Ürün adı bu stringi içermiyorsa elenir. |
| `sites` | `trendyol`, `hepsiburada`, `amazon_tr`. Kayıtlı olmayan site adı atlanır. |
| `history_days` | "Son X günün en düşüğü" penceresi (varsayılan 90). |
| `max_products_per_brand_per_site` | Performans için marka başına üst sınır. |
| `request_delay_ms` | İstekler arası bekleme (bot engellemeyi azaltır). |
| `headless` | `false` yaparsanız tarayıcı görünür olur (Hepsiburada için yardımcı olabilir). |
| `search_suffix` | Her arama sorgusuna eklenen ek kelime (ör. `"meinl kahve çekirdeği"`). Yalnızca çekirdek seçiliyken kullanılır; başka türler de seçilince otomatik olarak genel `"kahve"` aramasına geçilir. |
| `product_types` | Sonuçlara dahil edilecek ürün türleri: `cekirdek`, `ogutulmus`, `kapsul`, `filtre`, `turk`, `instant`. Varsayılan sadece `cekirdek`. |
| `start_with_windows` | Windows oturum açılışında otomatik başlat. (Kayıt defteri `HKCU\...\Run` ile yönetilir; uygulama içinden de açılıp kapatılabilir.) |
| `auto_scan_on_launch` | O gün uygulama ilk açıldığında otomatik bir tarama başlat (günde en fazla bir kez). |

> Bu ayarların çoğu uygulama içindeki **⚙ Filtreler** penceresinden değiştirilebilir; "Kaydet" dediğinizde `config.json` güncellenir. Elle de düzenleyebilirsiniz.

`config.json`'u hem geliştirme kökünde, hem paketli `exe`'nin yanında bırakabilirsiniz — `exe` yanındaki öncelikli.

---

## Nasıl çalışır?

1. Çift tıklayıp uygulamayı açarsınız.
2. Açılışta DB'deki son 48 saatin snapshot'ı yüklenir; varsa fırsatlar **Fırsatlar** sekmesinde görünür.
3. (İsteğe bağlı) **⚙ Filtreler** ile markaları, ürün türlerini, indirim penceresini ve otomatik başlatmayı ayarlarsınız.
4. **Taramayı Başlat** → seçili her site × her marka için Playwright headless Chromium arka planda arama yapar.
5. Bulunan her ürün `data/price_history.db` içindeki SQLite veritabanına yazılır (fiyat, üstü çizili eski fiyat, zaman damgası).
6. Ürün fiyatı son N günün (varsayılan 90) en düşüğünün ALTINA indiyse VEYA sitede üstü çizili eski fiyat varsa **Fırsatlar** sekmesine eklenir.
7. **Tüm Ürünler** sekmesi taranan her şeyi gösterir. Üstteki 🔍 arama kutusuyla sonuçlarda marka/ürün/site bazında filtreleme yapabilirsiniz.
8. Bir ürünün satırında 📈 **Grafik** butonuna basarak (veya satıra çift tıklayarak) 90 günlük fiyat geçmişini açabilirsiniz.
9. Pencereyi kapattığınızda: aktif tarama iptal edilir, Playwright kapanır, SQLite bağlantısı kapanır, süreç sonlanır. Arkaplanda hiçbir şey kalmaz.

### İlk gün problemi

İlk taramada geçmiş bazlı fırsatlar görünmez (geçmiş henüz yok). Ancak sitelerin üstü çizili indirim gösterdiği ürünler **site bazlı fırsat** olarak hemen listelenir. Birkaç tarama sonrası geçmiş bazlı tespit de devreye girer.

---

## Bilinen Sınırlamalar

| Site | Durum |
|---|---|
| Trendyol | ✅ Stabil |
| Amazon.com.tr | ✅ Stabil (nadiren CAPTCHA) |
| Hepsiburada | ⚠ Agresif bot koruması; headful modda daha iyi çalışır, headless'te "Güvenlik" sayfasında takılabilir |

Siteler HTML yapılarını değiştirdiğinde ilgili scraper (`src/scrapers/<site>.py`) güncellenmelidir. Her scraper dosyasının başında "son doğrulama tarihi" yer alır.

---

## Proje Yapısı

```
coffee-deal-tracker/
├── config.json              # markalar, siteler, ayarlar
├── requirements.txt
├── build.ps1                # PyInstaller paketleme
├── run.ps1                  # geliştirme çalıştırma
├── src/
│   ├── main.py              # giriş noktası (--autoscan argümanını destekler)
│   ├── ui/
│   │   ├── main_window.py   # pencere, buton, arama çubuğu, sekmeler
│   │   ├── deal_table.py    # ürün/fırsat tablosu (arama filtresi + sayısal sıralama)
│   │   ├── filter_dialog.py # marka/ürün türü/pencere/oto-başlatma ayar penceresi
│   │   └── price_chart.py   # 90 günlük fiyat geçmişi grafiği
│   ├── scrapers/
│   │   ├── base.py          # BaseScraper + ürün türü sınıflandırma
│   │   ├── trendyol.py
│   │   ├── hepsiburada.py
│   │   └── amazon_tr.py
│   ├── storage/
│   │   └── db.py            # SQLite wrapper
│   └── core/
│       ├── config.py        # AppConfig loader/saver + PRODUCT_TYPES
│       ├── autostart.py     # Windows başlangıç (registry Run) yönetimi
│       ├── models.py        # dataclass'lar
│       ├── scanner.py       # QThread scan worker
│       └── deal_detector.py # geçmiş (N-gün en düşük) + site indirim mantığı
└── data/
    └── price_history.db     # otomatik oluşur
```

---

## Scraper'ı Elle Test Etme

```powershell
python -m src.scrapers.trendyol meinl
python -m src.scrapers.amazon_tr tchibo
python -m src.scrapers.hepsiburada lavazza
```

Her modül `__main__` bloğu içerir; marka argümanıyla çağrıldığında bulunan ürünleri konsola döker.

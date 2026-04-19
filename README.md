# Coffee Deal Tracker

Trendyol, Hepsiburada ve Amazon.com.tr sitelerinde kaliteli kahve çekirdeği markalarını (Meinl, Tchibo, Lavazza vb.) tarayıp son 30 günün en düşük fiyatının altına inen ürünleri bulan bir Windows masaüstü uygulaması.

- **Dil/Framework**: Python 3.11+ · PySide6 · Playwright · SQLite
- **Bildirim**: Yalnızca uygulama içinde (Windows toast / e-posta / Telegram yok)
- **Arkaplan**: Yok — pencere kapatıldığında her şey durur

---

## Kurulum (geliştirici)

```powershell
cd C:\Users\taleb\Desktop\coffee-deal-tracker
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

## Yapılandırma (`config.json`)

```json
{
  "brands": ["meinl", "tchibo", "whirl", "lavazza", "illy", "kicking horse"],
  "sites": ["trendyol", "hepsiburada", "amazon_tr"],
  "history_days": 30,
  "max_products_per_brand_per_site": 15,
  "request_delay_ms": 2000,
  "headless": true,
  "search_suffix": "kahve çekirdeği"
}
```

| Alan | Açıklama |
|---|---|
| `brands` | Her sitede aranacak markalar (küçük harf). Ürün adı bu stringi içermiyorsa elenir. |
| `sites` | `trendyol`, `hepsiburada`, `amazon_tr`. Kayıtlı olmayan site adı atlanır. |
| `history_days` | "Son X günün en düşüğü" penceresi. |
| `max_products_per_brand_per_site` | Performans için marka başına üst sınır. |
| `request_delay_ms` | İstekler arası bekleme (bot engellemeyi azaltır). |
| `headless` | `false` yaparsanız tarayıcı görünür olur (Hepsiburada için yardımcı olabilir). |
| `search_suffix` | Her arama sorgusuna eklenen ek kelime (ör. `"meinl kahve çekirdeği"`). |

`config.json`'u hem geliştirme kökünde, hem paketli `exe`'nin yanında bırakabilirsiniz — `exe` yanındaki öncelikli.

---

## Nasıl çalışır?

1. Çift tıklayıp uygulamayı açarsınız.
2. **Taramayı Başlat** → her site × her marka için Playwright headless Chromium arka planda arama yapar.
3. Bulunan her ürün `data/price_history.db` içindeki SQLite veritabanına yazılır (fiyat + zaman damgası).
4. Ürün fiyatı **son 30 günün en düşüğünün altına** indiyse **Fırsatlar** sekmesine eklenir (aynı fiyat kalırsa fırsat sayılmaz — %0 indirim gürültüsü filtrelenir).
5. **Tüm Ürünler** sekmesi taranan her şeyi gösterir.
6. Pencereyi kapattığınızda: aktif tarama iptal edilir, Playwright kapanır, SQLite bağlantısı kapanır, süreç sonlanır. Arkaplanda hiçbir şey kalmaz.

### İlk gün problemi

İlk çalıştırmada fiyat geçmişi boş olduğu için hiçbir ürün "fırsat" sayılmaz. Bu normaldir — uygulamayı birkaç gün açık bırakın (veya birkaç kere açın), geçmiş birikince **Fırsatlar** sekmesi dolmaya başlar.

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
│   ├── main.py              # giriş noktası
│   ├── ui/
│   │   ├── main_window.py   # pencere, buton, sekmeler
│   │   └── deal_table.py    # ürün/fırsat tablosu
│   ├── scrapers/
│   │   ├── base.py          # BaseScraper + yardımcılar
│   │   ├── trendyol.py
│   │   ├── hepsiburada.py
│   │   └── amazon_tr.py
│   ├── storage/
│   │   └── db.py            # SQLite wrapper
│   └── core/
│       ├── config.py        # AppConfig loader
│       ├── models.py        # dataclass'lar
│       ├── scanner.py       # QThread scan worker
│       └── deal_detector.py # 30-gün en düşük mantığı
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

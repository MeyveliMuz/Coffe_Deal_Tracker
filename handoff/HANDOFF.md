# Coffee Deal Tracker — Sohbet Devir Notu (HANDOFF)

> Bu dosyayı yeni sohbette Claude'a okut: *"handoff/HANDOFF.md'yi oku, kaldığımız yerden devam edelim."*
> Son güncelleme: 2026-06-14

## 0. Tek cümle
Trendyol/Hepsiburada/Amazon'da kahve fiyatlarını tarayıp gerçek indirimleri bulan uygulama; **tek Python çekirdeği** üç istemciyle paylaşılıyor: masaüstü pencere, web (PWA), ve FastAPI backend.

## 1. Repo & ortam
- Repo: `C:\Users\Huseyin\Desktop\okul\coffee-deal-tracker` · GitHub: `MeyveliMuz/Coffe_Deal_Tracker`
- Branch: **master** (her şey burada). Yan branch'ler: `feat/web-platform` (merge edildi), `deploy` (derlenmiş `frontend/dist` içerir — sadece bulut deploy içindi).
- **Python 3.14** kullan (`py -3.14`). Varsayılan `python` 3.12'dir ve PySide6/bağımlılıklar 3.14'te. Tarayıcı eksikse: `py -3.14 -m playwright install chromium`.
- Frontend: Node 20+, `npm --prefix frontend ...`.

## 2. Mimari (önemli)
- **Çekirdek (UI'sız):** `src/core/scan_engine.py` → `async run_scan(config, db_path, on_progress, on_product, on_deal, on_error, should_cancel)` — tarama beyni, callback'lerle olay bildirir. `deal_detector.py` (iki yönlü fırsat: 90-gün en düşük + site strikethrough), `config.py` (AppConfig load/save + PRODUCT_TYPES), `models.py`.
- **Scrapers:** `src/scrapers/` — `base.py` (BaseScraper: fiyat parse, ürün-türü sınıflandırma, bot tespiti), `trendyol.py`, `hepsiburada.py`, `amazon_tr.py`, `_template.py` (yeni site şablonu).
- **Storage:** `src/storage/db.py` — SQLite (products, price_history, alerts), WAL, thread-safe.
- **Backend:** `backend/` — FastAPI. `main.py` (REST + WebSocket + en sonda `frontend/dist`'i StaticFiles ile sunar → tek origin), `scan_manager.py` (tarama job + WS yayını), `scheduler.py` (APScheduler günlük tarama), `services.py`, `notify.py` (opsiyonel SMTP alarm e-postası), `schemas.py`, `tests/`.
- **Frontend:** `frontend/` — React + Vite + Tailwind v4 + PWA. `src/App.tsx`, `src/api.ts` (API_BASE boş=aynı origin), `components/` (PriceChartModal, FiltersModal, AlertsModal, ScanBar).
- **Masaüstü:** `desktop.py` — PySide6 QtWebEngine penceresi; backend'i başlatır/kullanır, web UI'ı pencerede gösterir.
- Eski Qt arayüzü (src/ui, scanner.py, autostart.py, app_state.py) **silindi** (Faz 8).

## 3. Şu an NASIL çalışıyor (PC deploy — AKTİF)
Bulut (Oracle A1) denendi ama Frankfurt'ta ücretsiz kapasite çıkmadı; 1GB E2.1.Micro yetersizdi (OOM). **Kesin çözüm: backend kullanıcının PC'sinde 7/24 (PC açıkken).**
- `start_backend.vbs` backend'i **penceresiz** başlatır: `py -3.14 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 >> data\backend.log 2>&1`. (pythonw+uvicorn olmuyor — stdout None → uvicorn çöker; VBS gerçek py'yi penceresiz çalıştırır.)
- Aynı VBS **Startup klasöründe** (`...\Start Menu\Programs\Startup\CoffeeDealTracker-Backend.vbs`) → her oturum açışta otomatik başlar.
- Erişim: **http://localhost:8000** (PC, arayüz+API), telefon (aynı WiFi): **http://192.168.1.118:8000** (Windows Firewall'da 8000 inbound gerek — admin: `New-NetFirewallRule -DisplayName "Coffee 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private`).
- `config.json`: `schedule_enabled=true`, `schedule_time=10:00` → her gün otomatik tarama.
- **Masaüstü kısayolu:** `Desktop\Coffee Deal Tracker.lnk` → `pythonw desktop.py` (aynı backend'i pencerede gösterir).

### Yeniden başlatma / sorun giderme
- Backend yeniden başlat: 8000'deki süreci durdur, sonra `wscript.exe "<repo>\start_backend.vbs"`.
- Arayüz boş/404 ise `frontend/dist` eksiktir (gitignore'lu; **git branch değiştirince silinebilir**) → `npm --prefix frontend run build` → backend'i yeniden başlat.
- Log: `data\backend.log`.

## 4. ÇÖZÜLDÜ (2026-06-14): Hepsiburada'dan veri gelmiyordu
**Teşhis:** İki ayrı sorun vardı:
1. **Eski seçiciler.** Headful tarama bot korumasını GEÇİYOR ama 0 ürün dönüyordu → site arama sayfasını yeniden tasarlamış (CSS-module, karmalı sınıf adları). Eski `li.productListContent-item` / `[data-test-id='product-card']` seçicileri artık yok.
2. **Headless bloklanıyor.** Backend `headless: true` ile çalışıyor; Hepsiburada'nın bot koruması (DataDome/Akamai sınıfı) ESKİ headless Chromium'u JS-altı parmak iziyle yakalıyor → güvenlik sayfası. JS stealth (webdriver/plugins/window.chrome maskeleme) YETMİYOR.

**Çözüm:**
- `src/scrapers/hepsiburada.py`: yeni sabit tutamaçlarla yeniden yazıldı. Kartlar `<li>` içinde `data-test-id="title-N"` + `final-price-N` (N=1'den artan), üstü çizili fiyat sınıf adında `originalPrice`, link `productCardLink` içerir. Veri tek bir `page.evaluate` ile ham çekilip Python'da filtreleniyor (karmalı sınıf son eklerine bağımlı değil).
- `src/core/scan_engine.py`: `config.headless=True` iken Chromium artık ESKİ headless yerine **YENİ headless** modunda açılıyor (`launch(headless=False, args=[..., '--headless=new'])`). Yeni headless gerçek başlı tarayıcıya çok yakın, korumayı geçiyor ve pencere açmıyor. `config.headless=False` → gerçek headful (debug).
- Doğrulama (2026-06-14): uçtan uca tarama (headless=true, sadece hepsiburada, meinl+lavazza) → **10 ürün, 3 fırsat, 0 hata**. `py -3.14 -m pytest backend/tests -q` → 4 passed.

**Tekrar test (headful, tek başına):** `py -3.14 -X utf8 -m src.scrapers.hepsiburada meinl` (UTF-8 bayrağı olmadan Windows konsolu Türkçe karakterde çöker — sadece print sorunu, scraper değil).

## 5. Faz geçmişi (hepsi master'da, bitti)
Faz 0 scan_engine ayrımı · 1 FastAPI · 2 React/Tailwind · 3 alarm+zamanlama · 4 Docker+CI · 5 scraper şablonu+deploy artefakt · 6 PWA · 7 masaüstü wrapper · 8 Qt temizliği.

## 6. Yan dosyalar (repo dışı, Desktop/okul)
`coffee_a1_retry.ps1` + `shape.json` (Oracle A1 retry — şimdilik kullanılmıyor, A1 kapasite çıkarsa diye dursun). OCI CLI: `...Python312\Scripts\oci.exe`, profil `coffee` (token ~24h, süresi dolmuş olabilir → `oci session authenticate --profile-name coffee` ile yenile).

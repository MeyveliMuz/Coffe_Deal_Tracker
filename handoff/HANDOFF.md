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

## 4. AÇIK GÖREV (sonraki sohbette ÇÖZ): Hepsiburada'dan veri gelmiyor
**Belirti:** Tarama sonuçlarında Hepsiburada'dan hiç ürün yok (Trendyol + Amazon geliyor).
**Olası sebep:** Hepsiburada agresif bot koruması ("Güvenlik doğrulaması" sayfası) — headless Chromium bloklanıyor → `hepsiburada.py` `BotProtectionError` fırlatıp siteyi atlıyor (0 veri). Alternatif: site HTML'i değişti → `wait_for_selector` zaman aşımı → boş `[]` (hata yok ama veri yok).
**İlk teşhis adımı (next chat):**
```powershell
# Tek başına, GÖRÜNÜR tarayıcıyla çalıştır (headful) — ne oluyor gör:
py -3.14 -m src.scrapers.hepsiburada meinl
```
(Bu modülün `__main__` bloğu headful çalışır, bulunan ürünleri yazar; "Güvenlik" sayfası mı, selector mı ayırt edilir.) Ayrıca `data\backend.log`'ta tarama özetinde hepsiburada için "bot koruması" satırına bak.
**Çözüm seçenekleri:** (a) `playwright-stealth` / daha iyi evasion, (b) gerçek mobil/API uçları, (c) HB'yi "best-effort" kabul edip Trendyol/Amazon'a odaklan. İlgili dosya: `src/scrapers/hepsiburada.py` (warm-up + güvenlik tespiti + selector'lar burada).

## 5. Faz geçmişi (hepsi master'da, bitti)
Faz 0 scan_engine ayrımı · 1 FastAPI · 2 React/Tailwind · 3 alarm+zamanlama · 4 Docker+CI · 5 scraper şablonu+deploy artefakt · 6 PWA · 7 masaüstü wrapper · 8 Qt temizliği.

## 6. Yan dosyalar (repo dışı, Desktop/okul)
`coffee_a1_retry.ps1` + `shape.json` (Oracle A1 retry — şimdilik kullanılmıyor, A1 kapasite çıkarsa diye dursun). OCI CLI: `...Python312\Scripts\oci.exe`, profil `coffee` (token ~24h, süresi dolmuş olabilir → `oci session authenticate --profile-name coffee` ile yenile).

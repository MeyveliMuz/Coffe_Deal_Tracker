# PyInstaller ile Windows .exe paketleme scripti
# Kullanım: .\build.ps1
#
# Çıktı: dist/CoffeeDealTracker/CoffeeDealTracker.exe
#
# Not: Playwright Chromium tarayıcısı bundle'a dahil edilmez — ilk çalıştırmada
# otomatik %LOCALAPPDATA%\ms-playwright altına indirilir (~150 MB).

Set-Location $PSScriptRoot

# Önce pyinstaller var mı?
$hasPI = Get-Command pyinstaller -ErrorAction SilentlyContinue
if (-not $hasPI) {
    Write-Host "pyinstaller bulunamadı, kuruluyor..." -ForegroundColor Yellow
    pip install pyinstaller
}

# Eski build'i temizle
if (Test-Path "build")   { Remove-Item "build"   -Recurse -Force }
if (Test-Path "dist")    { Remove-Item "dist"    -Recurse -Force }
if (Test-Path "CoffeeDealTracker.spec") { Remove-Item "CoffeeDealTracker.spec" -Force }

Write-Host "PyInstaller çalıştırılıyor..." -ForegroundColor Cyan

pyinstaller `
    --noconfirm `
    --noconsole `
    --onedir `
    --name CoffeeDealTracker `
    --icon assets/icon.ico `
    --add-data "config.json;." `
    --add-data "assets/icon.ico;assets" `
    --collect-all playwright `
    --hidden-import PySide6.QtWidgets `
    --hidden-import PySide6.QtCore `
    --hidden-import PySide6.QtGui `
    src/main.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build başarısız!" -ForegroundColor Red
    exit 1
}

# config.json'u exe'nin yanına da koy (opsiyonel override için)
Copy-Item "config.json" "dist/CoffeeDealTracker/" -Force -ErrorAction SilentlyContinue

# data/ klasörü oluştur (SQLite dosyası buraya yazılacak)
New-Item -ItemType Directory -Force -Path "dist/CoffeeDealTracker/data" | Out-Null

# Playwright tarayıcılarını exe yanına kopyala (portable dağıtım)
Write-Host ""
Write-Host "Playwright tarayıcıları exe yanına kopyalanıyor..." -ForegroundColor Cyan
$src = Join-Path $env:LOCALAPPDATA "ms-playwright"
$dst = "dist/CoffeeDealTracker/browsers"
if (Test-Path $src) {
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    # Yalnızca gerekli olanlar: chromium_headless_shell + ffmpeg + winldd
    foreach ($name in @("chromium_headless_shell-*", "ffmpeg-*", "winldd-*")) {
        Get-ChildItem $src -Filter $name -Directory | ForEach-Object {
            Write-Host "  $($_.Name) kopyalanıyor..."
            Copy-Item $_.FullName -Destination $dst -Recurse -Force
        }
    }
    Write-Host "  Tarayıcılar hazır: $dst" -ForegroundColor Green
} else {
    Write-Host "  UYARI: $src bulunamadı. Önce 'python -m playwright install chromium' çalıştırın." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Build tamam! Çalıştırmak için:" -ForegroundColor Green
Write-Host "  dist\CoffeeDealTracker\CoffeeDealTracker.exe"

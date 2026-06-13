# Masaüstü uygulamasını (web arayüzlü wrapper) çalıştır.
# NOT: PySide6/Playwright Python 3.14'te kurulu; düz `python` 3.12'ye gidiyor.
Set-Location $PSScriptRoot
if (-not (Test-Path "frontend/dist")) {
    Write-Host "frontend/dist yok — derleniyor..."
    npm --prefix frontend install
    npm --prefix frontend run build
}
py -3.14 desktop.py

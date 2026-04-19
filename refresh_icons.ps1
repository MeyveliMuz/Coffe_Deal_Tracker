# Windows ikon cache'ini temizler — yeni exe ikonu görünsün diye.
# Kullanım: sağ tıkla > "Run with PowerShell", veya:
#   powershell -ExecutionPolicy Bypass -File .\refresh_icons.ps1

Write-Host "Windows ikon cache'i temizleniyor..." -ForegroundColor Cyan

# 1) Explorer'ı kapat
Write-Host "  Explorer kapatılıyor..."
Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# 2) Cache dosyalarını sil
$paths = @(
    "$env:LOCALAPPDATA\IconCache.db",
    "$env:LOCALAPPDATA\Microsoft\Windows\Explorer\iconcache_*.db",
    "$env:LOCALAPPDATA\Microsoft\Windows\Explorer\thumbcache_*.db"
)
foreach ($p in $paths) {
    Get-Item -Path $p -Force -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            Remove-Item $_.FullName -Force -ErrorAction Stop
            Write-Host "  Silindi: $($_.Name)" -ForegroundColor Green
        } catch {
            Write-Host "  Silinemedi (kilitli olabilir): $($_.Name)" -ForegroundColor Yellow
        }
    }
}

# 3) Explorer'ı yeniden başlat
Write-Host "  Explorer başlatılıyor..."
Start-Process explorer

Write-Host ""
Write-Host "Bitti. Klasör penceresini kapatıp tekrar açın — kahve çekirdeği ikonu görünmeli." -ForegroundColor Green

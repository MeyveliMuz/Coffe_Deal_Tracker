Add-Type -AssemblyName System.Drawing
$exe = 'C:\Users\taleb\Desktop\coffee-deal-tracker\dist\CoffeeDealTracker\CoffeeDealTracker.exe'
$ico = [System.Drawing.Icon]::ExtractAssociatedIcon($exe)
$bmp = $ico.ToBitmap()
$out = 'C:\Users\taleb\Desktop\coffee-deal-tracker\assets\exe_current_icon.png'
$bmp.Save($out)
Write-Host ('Saved ' + $bmp.Width + 'x' + $bmp.Height + ' to ' + $out)

' Coffee Deal Tracker backend'i PENCERESIZ baslatir (cikti data\backend.log'a).
' pythonw yerine bunu kullaniriz: gercek stdout/stderr (dosya) olur, uvicorn cokmez.
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Huseyin\Desktop\okul\coffee-deal-tracker"
sh.Run "cmd /c py -3.14 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 >> data\backend.log 2>&1", 0, False

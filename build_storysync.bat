@echo off
echo Building StorySync v5...
cd /d "%~dp0"

pyinstaller --onefile --windowed ^
  --name StorySync ^
  --collect-data customtkinter ^
  --hidden-import storysync ^
  --hidden-import storysync.gui ^
  --hidden-import storysync.transcription ^
  --hidden-import storysync.render ^
  --add-data "C:\Windows\Fonts\georgiab.ttf;fonts" ^
  --add-data "C:\Windows\Fonts\georgia.ttf;fonts" ^
  --add-data "C:\Windows\Fonts\timesbd.ttf;fonts" ^
  --add-data "C:\Windows\Fonts\times.ttf;fonts" ^
  --add-data "C:\Windows\Fonts\NotoSerif-Bold.ttf;fonts" ^
  --add-data "C:\Windows\Fonts\NotoSerif-Regular.ttf;fonts" ^
  --add-data "C:\Windows\Fonts\cambriab.ttf;fonts" ^
  --add-data "C:\Windows\Fonts\BKANT.TTF;fonts" ^
  --add-data "C:\Windows\Fonts\courbd.ttf;fonts" ^
  --add-data "C:\Windows\Fonts\cour.ttf;fonts" ^
  storysync.py

echo.
if exist dist\StorySync.exe (
    echo SUCCESS: dist\StorySync.exe is ready.
) else (
    echo BUILD FAILED - check the output above.
)
pause

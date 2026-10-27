@echo off
setlocal
cd /d "%~dp0"
echo Offbeat - update the YouTube download engine
echo Close Offbeat before running this updater.
echo.
"%~dp0bin\yt-dlp.exe" --ignore-config -U
echo.
pause

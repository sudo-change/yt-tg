@echo off
REM yt2tg setup for Windows
REM Usage: double-click or run in CMD

echo === yt2tg Setup (Windows) ===

python -m venv .venv
call .venv\Scripts\activate.bat

pip install --upgrade pip
pip install pyrogram yt-dlp

REM tgcrypto needs Visual C++ Build Tools — try, don't fail if missing
pip install tgcrypto 2>nul || echo [INFO] tgcrypto skipped (needs Visual C++ Build Tools — optional)

echo.
echo Done! Next steps:
echo   1. Place your cookies.txt in this folder
echo   2. python yt2tg.py --setup
echo   3. python yt2tg.py "YOUTUBE_URL"
pause

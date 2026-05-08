@echo off
title AI Video Automation
cd /d "%~dp0"
python tools\convert_assets_to_gif.py
python app.py
pause

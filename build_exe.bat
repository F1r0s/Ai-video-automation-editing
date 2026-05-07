@echo off
echo Building AI Video Automation as a standalone executable...
echo Make sure you have pyinstaller installed (pip install pyinstaller)
pyinstaller --onefile --windowed --add-data "templates;templates" --add-data "secrets;secrets" --icon=NONE web_app.py
echo Build complete. Look in the "dist" folder for web_app.exe!
pause

@echo off
echo Building AI Video Automation as a standalone executable...
echo Make sure you have pyinstaller installed (pip install pyinstaller)
pyinstaller --onefile --windowed --icon=NONE app.py
echo Build complete. Look in the "dist" folder for app.exe!
pause

@echo off
"%~dp0runtime\python.exe" -I "%~dp0install.py" %*
if errorlevel 1 (
  echo.
  echo Installation failed. See the message above.
  pause
  exit /b 1
)
echo.
echo Installation finished. Select the imported layout in Herdr Settings - Look.
pause

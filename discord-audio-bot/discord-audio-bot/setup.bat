@echo off
cd /d "%~dp0"
echo Installing Discord music presence dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Dependency installation failed. Check Python and your internet connection, then run setup.bat again.
  pause
  exit /b 1
)
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo.
  echo Created .env. Add your Discord Application ID, then run start.bat.
)
echo.
echo Installing background auto-start...
wscript.exe //B //Nologo "%~dp0install_startup.vbs"
if errorlevel 1 (
  echo Could not install auto-start. Run install_startup.vbs manually.
)
echo.
echo The companion runs without a console. Windows notifications show connection and errors.
echo Discord must be open on this PC for music activity to appear.
pause

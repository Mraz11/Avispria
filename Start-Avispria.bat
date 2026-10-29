@echo off
rem Starts Avispria and opens it in your web browser.
rem Close this window to stop Avispria. Everything stays on this computer.
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo Avispria needs the program "uv" to run.
  echo Install it from https://docs.astral.sh/uv/ and then double-click this file again.
  pause
  exit /b 1
)
echo Starting Avispria... your browser will open in a moment.
uv run avispria ui
pause

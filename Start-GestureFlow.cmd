@echo off
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo Run Install.cmd in this folder first.
  pause
  exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"

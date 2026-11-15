@echo off
setlocal
cd /d "%~dp0"
if not exist .venv (
  echo Creating Python virtual environment...
  py -3.11 -m venv .venv
  if errorlevel 1 py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Starting Jarvis Multi-Agent at http://127.0.0.1:8787
echo Keep this terminal open. Press Ctrl+C to stop.
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8787

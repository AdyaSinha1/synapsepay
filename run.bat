@echo off
setlocal
set "ROOT=%~dp0"

echo ==================================================
echo   SynapsePay — Autonomous Agent Escrow Protocol
echo ==================================================
echo.

echo [1/4] Preparing Python virtual environment...
if not exist "%ROOT%backend\.venv" (
    python -m venv "%ROOT%backend\.venv"
    if errorlevel 1 (
        echo ERROR: Could not create venv. Is Python 3.11+ installed and on PATH?
        pause
        exit /b 1
    )
)
call "%ROOT%backend\.venv\Scripts\activate.bat"

echo [2/4] Installing backend dependencies...
python -m pip install --quiet --disable-pip-version-check -r "%ROOT%backend\requirements.txt"

echo [3/4] Launching backend on http://localhost:8000 ...
start "SynapsePay API :8000" /D "%ROOT%backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"

echo [4/4] Preparing frontend (first run downloads packages)...
cd /d "%ROOT%frontend"
if not exist node_modules (
    call npm.cmd install --no-audit --no-fund
    if errorlevel 1 (
        echo ERROR: npm install failed. Is Node.js 18+ installed?
        pause
        exit /b 1
    )
)
start "SynapsePay Dashboard :5173" /D "%ROOT%frontend" cmd /k "npm.cmd run dev"

timeout /t 6 /nobreak >nul
start http://localhost:5173

echo.
echo SynapsePay is running:
echo   Dashboard : http://localhost:5173
echo   API docs  : http://localhost:8000/docs
echo.
echo Close the two spawned windows to stop SynapsePay.
endlocal

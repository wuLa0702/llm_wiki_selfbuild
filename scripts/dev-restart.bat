@echo off
title LLM Wiki - Dev Restart

echo ========================================
echo   LLM Wiki - Dev Restart
echo ========================================
echo.

:: -- switch to project root --
cd /d "%~dp0.."
echo [WORKDIR] %cd%
echo.

:: -- kill old processes --
echo [CLEANUP] Killing old processes...

:: backend (port 8766)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8766 " ^| findstr LISTENING') do (
  echo   kill backend PID: %%p
  taskkill /f /pid %%p >nul 2>&1
)

:: frontend (port 5176)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5176 " ^| findstr LISTENING') do (
  echo   kill frontend PID: %%p
  taskkill /f /pid %%p >nul 2>&1
)

:: residual Python processes (uvicorn)
for /f "tokens=2" %%p in ('tasklist /fi "imagename eq python.exe" /fo csv /nh 2^>nul ^| findstr /i "uvicorn"') do (
  taskkill /f /pid %%p >nul 2>&1
)

timeout /t 1 /nobreak >nul
echo [CLEANUP] Done
echo.

:: -- start backend --
echo [BACKEND] Starting uvicorn (port 8766)...
start "LLM-Wiki-Backend" cmd /c "python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8766 --log-level warning"

:: -- start frontend --
echo [FRONTEND] Starting Vite dev server (port 5176)...
start "LLM-Wiki-Frontend" cmd /c "cd /d wiki-ui-v2 && npm run dev"

:: -- wait for startup --
echo.
echo [WAIT] Waiting for services to start...
timeout /t 4 /nobreak >nul

:: -- check backend --
echo [CHECK] Checking backend...
netstat -ano 2>nul | findstr ":8766 " | findstr LISTENING >nul
if %errorlevel% equ 0 (
  echo [OK] Backend is running on http://127.0.0.1:8766
) else (
  echo [WARN] Backend may not be ready yet - check the backend window for errors
)

:: -- check frontend --
echo [CHECK] Checking frontend...
netstat -ano 2>nul | findstr ":5176 " | findstr LISTENING >nul
if %errorlevel% equ 0 (
  echo [OK] Frontend is running on http://localhost:5176
) else (
  echo [WARN] Frontend may not be ready yet - check the frontend window for errors
)

:: -- open browser --
echo.
echo [BROWSER] Opening http://localhost:5176
start http://localhost:5176

echo.
echo ========================================
echo   Restart complete
echo   Backend : http://127.0.0.1:8766
echo   Frontend: http://localhost:5176
echo ========================================
echo.
echo Press any key to close this window...
echo (Backend and frontend windows will keep running)
pause >nul

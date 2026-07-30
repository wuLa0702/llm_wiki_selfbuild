@echo off
title LLM Wiki - Dev Restart

:: -- force UTF-8 for console output (fix garbled Chinese in UTF-8 terminals) --
@chcp 65001 >nul

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

:: uvicorn / app (port 8766)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8766 " ^| findstr LISTENING') do (
  echo   kill app PID: %%p
  taskkill /f /pid %%p >nul 2>&1
)

:: Vite dev server (port 5176)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5176 " ^| findstr LISTENING') do (
  echo   kill Vite dev server PID: %%p
  taskkill /f /pid %%p >nul 2>&1
)

:: residual Python processes (uvicorn)
for /f "tokens=2" %%p in ('tasklist /fi "imagename eq python.exe" /fo csv /nh 2^>nul ^| findstr /i "uvicorn"') do (
  taskkill /f /pid %%p >nul 2>&1
)

timeout /t 1 /nobreak >nul
echo [CLEANUP] Done
echo.

:: -- ensure log dir --
if not exist ".logs" mkdir ".logs"

:: -- start uvicorn (port 8766: serves API + built frontend dist/) --
echo [APP] Starting uvicorn (port 8766 — API + Frontend)...
start /b "" cmd /c "chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8766 --log-level warning > .logs\app.log 2>&1"

:: -- wait for uvicorn to be truly ready --
echo.
echo [WAIT] Waiting for uvicorn to respond (polling /health)...
set APP_READY=
for /l %%i in (1,1,30) do (
  >nul 2>&1 curl -s http://127.0.0.1:8766/health && (
    set APP_READY=1
    goto :app_ok
  )
  >nul 2>&1 timeout /t 1 /nobreak
)
:app_ok
if defined APP_READY (
  echo [OK] App is ready on http://127.0.0.1:8766
) else (
  echo [WARN] App health check timed out - check .logs\app.log for errors
  echo [INFO] Continuing anyway, Vite dev server will retry automatically...
)

:: -- wait a beat, then start Vite dev server --
>nul 2>&1 timeout /t 1 /nobreak

:: -- start Vite dev server (no popup, logs to file, UTF-8) --
set LOGDIR=%cd%\.logs
echo [VITE] Starting Vite dev server (port 5176 — hot reload)...
start /b "" cmd /c "chcp 65001 >nul && cd /d wiki-ui-v2 && npm run dev > %LOGDIR%\vite.log 2>&1"

:: -- check Vite dev server --
>nul 2>&1 timeout /t 3 /nobreak
netstat -ano 2>nul | findstr ":5176 " | findstr LISTENING >nul
if %errorlevel% equ 0 (
  echo [OK] Vite dev server is running on http://localhost:5176
) else (
  echo [WARN] Vite dev server not started - check .logs\vite.log for errors
)

:: -- open browser --
echo.
echo [BROWSER] Opening http://localhost:8766
start http://localhost:8766

echo.
echo ========================================
echo   Restart complete
echo   App (API + Frontend) : http://127.0.0.1:8766
echo   Vite dev server      : http://localhost:5176  (optional, hot reload)
echo ========================================
echo.
echo Press any key to close this window...
echo (Processes run in background, logs in .logs\)
pause >nul

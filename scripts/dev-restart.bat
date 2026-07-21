@echo off
chcp 65001 >nul
title 🔄 LLM Wiki — 一键重启

echo ╔══════════════════════════════════════╗
echo ║   LLM Wiki — Dev Restart            ║
echo ╚══════════════════════════════════════╝
echo.

:: ─── 切换到项目根目录 ───
cd /d "%~dp0.."
echo 📂 工作目录: %cd%
echo.

:: ─── 关闭已有进程 ───
echo 🔪 清理旧进程...

:: 后端 (port 8766)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8766 " ^| findstr LISTENING') do (
  echo   杀死后端 PID: %%p
  taskkill /f /pid %%p >nul 2>&1
)

:: 前端 (port 5176)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5176 " ^| findstr LISTENING') do (
  echo   杀死前端 PID: %%p
  taskkill /f /pid %%p >nul 2>&1
)

:: 残余 Python/Node 进程（当前项目目录下）
for /f "tokens=2" %%p in ('tasklist /fi "imagename eq python.exe" /fo csv /nh 2^>nul ^| findstr /i "uvicorn"') do (
  taskkill /f /pid %%p >nul 2>&1
)

timeout /t 1 /nobreak >nul
echo ✅ 旧进程已清理
echo.

:: ─── 启动后端 ───
echo 🚀 启动后端 (uvicorn)...
start "LLM-Wiki-Backend" cmd /c "python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8766 --log-level warning"
if %errorlevel% neq 0 (
  echo ❌ 后端启动失败
  pause
  exit /b 1
)

:: ─── 启动前端 ───
echo 🚀 启动前端 (Vite)...
start "LLM-Wiki-Frontend" cmd /c "cd /d wiki-ui-v2 && npm run dev"
if %errorlevel% neq 0 (
  echo ❌ 前端启动失败
  pause
  exit /b 1
)

:: ─── 等待启动 ───
echo.
echo ⏳ 等待服务启动...
timeout /t 3 /nobreak >nul

:: ─── 打开浏览器 ───
echo 🌐 打开浏览器...
start http://localhost:5176

echo.
echo ╔══════════════════════════════════════╗
echo ║   ✅ 重启完成                       ║
echo ║   后端: http://127.0.0.1:8766       ║
echo ║   前端: http://localhost:5176       ║
echo ╚══════════════════════════════════════╝
echo.
echo 按任意键关闭此窗口...
echo （后端和前端窗口会继续运行）
pause >nul
